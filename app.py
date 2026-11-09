
import csv
import html
import io
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from utils.asset_checker import (
    ASSET_SIMILARITY_THRESHOLD,
    compare_images
)

try:
    from utils.brand_checker import check_content
except ImportError:
    def check_content(content, guidelines):
        findings = []

        for term in guidelines.get("prohibited_terms", []):
            pattern = re.compile(
                r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)",
                re.IGNORECASE
            )

            for match in pattern.finditer(content):
                findings.append({
                    "type": "Prohibited Term",
                    "severity": "High",
                    "message": f"Prohibited term '{term}' found.",
                    "evidence": match.group(),
                    "guideline": f"Do not use: {term}",
                    "start": match.start(),
                    "end": match.end()
                })

        for phrase in guidelines.get("required_phrases", []):
            if phrase.casefold() not in content.casefold():
                findings.append({
                    "type": "Missing Required Phrase",
                    "severity": "Medium",
                    "message": f"Required phrase '{phrase}' is missing.",
                    "evidence": "Not found",
                    "guideline": f"Required phrase: {phrase}",
                    "start": None,
                    "end": None
                })

        return findings


# ---------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------

st.set_page_config(
    page_title="KnowledgeBridge",
    page_icon="🔗",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background-color: #0B1120;
    color: #E5E7EB;
}

[data-testid="stSidebar"] {
    background-color: #101A30;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    max-width: 1250px;
}

div[data-testid="stMetric"] {
    background: #111C33;
    border: 1px solid #263B60;
    padding: 16px;
    border-radius: 12px;
}

.stButton > button {
    background: #2563EB;
    color: white;
    border: 0;
    border-radius: 8px;
    min-height: 40px;
}

.stButton > button:hover {
    background: #1D4ED8;
    color: white;
}

.kb-subtitle {
    color: #94A3B8;
    font-size: 15px;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

DEFAULTS = {
    "findings": None,
    "review_status": {},
    "checks_run": 0,
    "last_checked_at": None,
    "last_content": "",
    "last_guidelines": {},
    "guideline_warnings": [],
    "asset_check_summary": None
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------
# FILE EXTRACTION
# ---------------------------------------------------------

def extract_file_text(uploaded_file):

    if uploaded_file is None:
        return ""

    data = uploaded_file.getvalue()
    extension = uploaded_file.name.lower().rsplit(".", 1)[-1]

    if extension == "txt":
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("latin-1")

    if extension == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))

        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        ).strip()

    if extension == "docx":
        from docx import Document

        document = Document(io.BytesIO(data))

        parts = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        for table in document.tables:
            for row in table.rows:
                parts.append(
                    " | ".join(
                        cell.text.strip()
                        for cell in row.cells
                    )
                )

        return "\n".join(parts).strip()

    raise ValueError(
        "Unsupported file type. Use TXT, PDF or DOCX."
    )


# ---------------------------------------------------------
# GUIDELINE PARSER
# ---------------------------------------------------------

def parse_guidelines(text):

    guidelines = {
        "prohibited_terms": [],
        "required_phrases": [],
        "approved_facts": []
    }

    warnings = []
    facts_by_key = {}

    prohibited_labels = {
        "prohibited",
        "prohibited term",
        "prohibited terms",
        "banned",
        "forbidden",
        "avoid"
    }

    required_labels = {
        "required",
        "required phrase",
        "required phrases",
        "mandatory",
        "mandatory phrase",
        "mandatory phrases"
    }

    fact_labels = {
        "fact",
        "approved fact",
        "approved facts"
    }

    for line_number, raw_line in enumerate(
        text.splitlines(), start=1
    ):

        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        label, separator, value = line.partition(":")

        if not separator:
            warnings.append(
                f"Line {line_number}: Missing ':' separator — {line}"
            )
            continue

        label = re.sub(
            r"[_-]+",
            " ",
            label.lower().strip()
        )

        value = value.strip()

        if not value:
            warnings.append(
                f"Line {line_number}: No value was provided."
            )
            continue

        if label in prohibited_labels:

            values = [
                item.strip()
                for item in re.split(r"[;,]", value)
                if item.strip()
            ]

            guidelines["prohibited_terms"].extend(values)

        elif label in required_labels:

            values = [
                item.strip()
                for item in re.split(r"[;,]", value)
                if item.strip()
            ]

            guidelines["required_phrases"].extend(values)

        elif label in fact_labels:

            fact_key, equals, approved_value = value.partition("=")

            fact_key = fact_key.strip()
            approved_value = approved_value.strip()

            if not equals or not fact_key or not approved_value:
                warnings.append(
                    f"Line {line_number}: Use "
                    "'Fact: key = approved value'."
                )
                continue

            identity = fact_key.casefold()

            if identity in facts_by_key:

                existing_value = facts_by_key[identity]["value"]

                if existing_value.casefold() != approved_value.casefold():
                    warnings.append(
                        f"Line {line_number}: Conflicting approved values "
                        f"for '{fact_key}'. The first value was retained."
                    )

                continue

            fact = {
                "key": fact_key,
                "value": approved_value
            }

            facts_by_key[identity] = fact
            guidelines["approved_facts"].append(fact)

        else:
            warnings.append(
                f"Line {line_number}: Unsupported rule label '{label}'."
            )

    guidelines["prohibited_terms"] = list(
        dict.fromkeys(guidelines["prohibited_terms"])
    )

    guidelines["required_phrases"] = list(
        dict.fromkeys(guidelines["required_phrases"])
    )

    return guidelines, warnings


# ---------------------------------------------------------
# APPROVED FACT CHECKING
# ---------------------------------------------------------

def get_sentence_bounds(content, position):

    delimiters = ".!?\n"

    previous_positions = [
        content.rfind(delimiter, 0, position)
        for delimiter in delimiters
    ]

    sentence_start = max(previous_positions) + 1

    next_positions = []

    for delimiter in delimiters:
        found = content.find(delimiter, position)

        if found != -1:
            next_positions.append(found)

    sentence_end = (
        min(next_positions) + 1
        if next_positions
        else len(content)
    )

    return sentence_start, sentence_end


def check_approved_facts(content, approved_facts):

    findings = []

    for fact in approved_facts:

        fact_key = fact["key"]
        approved_value = fact["value"]

        key_pattern = re.compile(
            r"(?<!\w)" + re.escape(fact_key) + r"(?!\w)",
            re.IGNORECASE
        )

        value_pattern = re.compile(
            r"(?<!\w)" + re.escape(approved_value) + r"(?!\w)",
            re.IGNORECASE
        )

        checked_sentences = set()

        for match in key_pattern.finditer(content):

            sentence_start, sentence_end = get_sentence_bounds(
                content,
                match.start()
            )

            sentence_identity = (
                sentence_start,
                sentence_end
            )

            if sentence_identity in checked_sentences:
                continue

            checked_sentences.add(sentence_identity)

            sentence = content[
                sentence_start:sentence_end
            ].strip()

            if not value_pattern.search(sentence):

                findings.append({
                    "type": "Approved Fact Review",
                    "severity": "Medium",
                    "message": (
                        f"The approved value '{approved_value}' "
                        f"was not found in the sentence mentioning "
                        f"'{fact_key}'. Human review is required."
                    ),
                    "evidence": sentence,
                    "guideline": (
                        f"Approved fact: "
                        f"{fact_key} = {approved_value}"
                    ),
                    "start": sentence_start,
                    "end": sentence_end
                })

    return findings


# ---------------------------------------------------------
# HIGHLIGHT FINDINGS IN ORIGINAL CONTENT
# ---------------------------------------------------------

def make_highlighted_html(content, findings):

    spans = []

    for finding in findings:

        start = finding.get("start")
        end = finding.get("end")

        if (
            isinstance(start, int)
            and isinstance(end, int)
            and 0 <= start < end <= len(content)
        ):
            spans.append((start, end))

    spans.sort()

    parts = []
    cursor = 0

    for start, end in spans:

        if start < cursor:
            continue

        parts.append(html.escape(content[cursor:start]))

        parts.append(
            '<mark style="background:#FDE68A;'
            'color:#111827;padding:2px 4px;border-radius:4px;">'
            + html.escape(content[start:end])
            + '</mark>'
        )

        cursor = end

    parts.append(html.escape(content[cursor:]))

    return "".join(parts).replace("\n", "<br>")


# ---------------------------------------------------------
# REPORT GENERATION
# ---------------------------------------------------------

def make_text_report(
    findings,
    statuses,
    checked_at,
    warnings,
    asset_summary=None
):

    lines = [
        "KNOWLEDGEBRIDGE",
        "BRAND GOVERNANCE REVIEW REPORT",
        "=" * 42,
        f"Checked at: {checked_at or 'Not available'}",
        f"Total detected issues: {len(findings)}",
        ""
    ]

    if not findings:
        lines.append(
            "No violations were detected against the supplied rules."
        )

    for index, finding in enumerate(findings):

        lines.extend([
            f"Issue {index + 1}",
            "-" * 30,
            f"Type: {finding.get('type', '')}",
            f"Severity: {finding.get('severity', '')}",
            f"Message: {finding.get('message', '')}",
            f"Evidence: {finding.get('evidence', '')}",
            f"Guideline: {finding.get('guideline', '')}",
            f"Human review: {statuses.get(index, 'Pending')}",
            ""
        ])

    if warnings:

        lines.append("UNSUPPORTED GUIDELINE INSTRUCTIONS")

        for warning in warnings:
            lines.append(f"- {warning}")

        lines.append("")

    if asset_summary:

        lines.extend([
            "BRAND ASSET COMPARISON",
            "-" * 30,
            f"Status: {asset_summary.get('status', 'Not available')}",
            f"Approved asset: {asset_summary.get('approved_filename', '')}",
            f"Submitted asset: {asset_summary.get('submitted_filename', '')}",
            f"Pixel similarity: {asset_summary.get('similarity_score', 'Not calculated')}",
            f"Flag threshold: {asset_summary.get('threshold', ASSET_SIMILARITY_THRESHOLD)}%",
            f"Details: {asset_summary.get('message', '')}",
            "Image comparison is a basic normalized pixel comparison, not semantic "
            "recognition, trademark verification or proof of authenticity.",
            ""
        ])

    lines.append(
        "A human reviewer is responsible for the final decision."
    )

    lines.append(
        "Approved-fact checks use exact same-sentence value matching. "
        "They are not semantic or external fact verification."
    )

    return "\n".join(lines)


def make_csv_report(findings, statuses, asset_summary=None):

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Issue Number",
        "Issue Type",
        "Severity",
        "Message",
        "Evidence",
        "Guideline",
        "Review Status"
    ])

    for index, finding in enumerate(findings):

        writer.writerow([
            index + 1,
            finding.get("type", ""),
            finding.get("severity", ""),
            finding.get("message", ""),
            finding.get("evidence", ""),
            finding.get("guideline", ""),
            statuses.get(index, "Pending")
        ])

    if asset_summary:
        writer.writerow([
            "SUMMARY",
            "Brand Asset Comparison",
            "Informational",
            asset_summary.get("message", ""),
            (
                f"Approved: {asset_summary.get('approved_filename', '')}; "
                f"Submitted: {asset_summary.get('submitted_filename', '')}; "
                f"Pixel similarity: {asset_summary.get('similarity_score', 'Not calculated')}"
            ),
            f"Flag threshold: {asset_summary.get('threshold', ASSET_SIMILARITY_THRESHOLD)}%",
            asset_summary.get("status", "Not available")
        ])

    return output.getvalue()


# ---------------------------------------------------------
# SIDEBAR NAVIGATION
# ---------------------------------------------------------

with st.sidebar:

    st.markdown("# 🔗 KnowledgeBridge")
    st.caption("Brand Governance Assistant")
    st.divider()

    page = st.radio(
        "Navigation",
        ["Content Checker", "Dashboard", "About"],
        label_visibility="collapsed"
    )

    st.divider()
    st.caption("TEAM BUGBUSTERS")
    st.caption("Asansol Engineering College")


# ---------------------------------------------------------
# CONTENT CHECKER
# ---------------------------------------------------------

if page == "Content Checker":

    st.title("Brand Governance Check")

    st.markdown(
        '<p class="kb-subtitle">'
        'Check submitted content against approved brand guidelines.'
        '</p>',
        unsafe_allow_html=True
    )

    st.divider()

    left, right = st.columns(2)

    with left:

        st.subheader("1. Content to Review")

        content_file = st.file_uploader(
            "Upload content (TXT, PDF or DOCX)",
            type=["txt", "pdf", "docx"],
            key="content_upload"
        )

        content_manual = st.text_area(
            "Or paste content here",
            height=210,
            placeholder="Paste your advertisement, marketing copy or document text.",
            key="content_manual"
        )

    with right:

        st.subheader("2. Approved Brand Guidelines")

        guideline_file = st.file_uploader(
            "Upload guidelines (TXT, PDF or DOCX)",
            type=["txt", "pdf", "docx"],
            key="guideline_upload"
        )

        guideline_manual = st.text_area(
            "Or paste guidelines here",
            height=210,
            placeholder=(
                "Prohibited: guaranteed\n"
                "Required: Terms and conditions apply\n"
                "Fact: warranty = 2 years"
            ),
            key="guideline_manual"
        )

    st.divider()

    st.subheader("3. Approved Brand Asset Review")

    st.caption(
        "Compare a submitted image with an approved reference image. "
        "The comparison is a basic pixel-based aid; a human reviewer "
        "makes the final decision."
    )

    asset_input_mode = st.radio(
        "Choose how to provide the asset images",
        ["Use included demo assets", "Upload your own assets"],
        horizontal=True,
        key="asset_input_mode"
    )

    approved_asset_file = None
    submitted_asset_file = None
    approved_asset_bytes = None
    submitted_asset_bytes = None
    approved_asset_name = ""
    submitted_asset_name = ""
    asset_load_error = None

    if asset_input_mode == "Use included demo assets":

        demo_case = st.selectbox(
            "Demo comparison case",
            [
                "Modified sample (expected to be flagged)",
                "Identical sample (expected to pass)"
            ],
            key="demo_asset_case"
        )

        demo_asset_directory = Path(__file__).parent / "assets"
        approved_asset_path = demo_asset_directory / "demo_approved_logo.png"

        if demo_case.startswith("Modified"):
            submitted_asset_path = demo_asset_directory / "demo_modified_logo.png"
        else:
            submitted_asset_path = approved_asset_path

        try:
            approved_asset_bytes = approved_asset_path.read_bytes()
            submitted_asset_bytes = submitted_asset_path.read_bytes()
            approved_asset_name = approved_asset_path.name
            submitted_asset_name = submitted_asset_path.name

            preview_left, preview_right = st.columns(2)

            with preview_left:
                st.image(
                    approved_asset_bytes,
                    caption="Approved reference — demo only",
                    use_container_width=True
                )

            with preview_right:
                st.image(
                    submitted_asset_bytes,
                    caption="Submitted image — demo only",
                    use_container_width=True
                )

            st.info(
                "These are synthetic demonstration images, not an official "
                "KnowledgeBridge or third-party brand identity."
            )

        except OSError as error:
            asset_load_error = (
                "Demo image files could not be loaded. Make sure the "
                "assets folder from the supplied project package is present. "
                f"Details: {error}"
            )

    else:

        asset_left, asset_right = st.columns(2)

        with asset_left:
            approved_asset_file = st.file_uploader(
                "Upload approved reference image",
                type=["png", "jpg", "jpeg", "webp"],
                key="approved_asset_upload"
            )

        with asset_right:
            submitted_asset_file = st.file_uploader(
                "Upload submitted image",
                type=["png", "jpg", "jpeg", "webp"],
                key="submitted_asset_upload"
            )

        if approved_asset_file is not None:
            approved_asset_bytes = approved_asset_file.getvalue()
            approved_asset_name = approved_asset_file.name

        if submitted_asset_file is not None:
            submitted_asset_bytes = submitted_asset_file.getvalue()
            submitted_asset_name = submitted_asset_file.name

        preview_left, preview_right = st.columns(2)

        with preview_left:
            if approved_asset_bytes:
                st.image(
                    approved_asset_bytes,
                    caption=f"Approved reference — {approved_asset_name}",
                    use_container_width=True
                )

        with preview_right:
            if submitted_asset_bytes:
                st.image(
                    submitted_asset_bytes,
                    caption=f"Submitted image — {submitted_asset_name}",
                    use_container_width=True
                )

        if (approved_asset_file is None) != (submitted_asset_file is None):
            st.warning(
                "Upload both images to run the asset comparison. "
                "You may leave both empty to run text checks only."
            )

    asset_upload_incomplete = (
        asset_input_mode == "Upload your own assets"
        and ((approved_asset_file is None) != (submitted_asset_file is None))
    )

    content_text = content_manual
    guideline_text = guideline_manual
    file_error = False

    if content_file is not None:

        try:
            content_text = extract_file_text(content_file)

            st.caption(
                f"Content source: {content_file.name}"
            )

            if content_text:

                with st.expander("Preview extracted content"):
                    st.text(content_text[:3000])

            else:
                st.warning(
                    "No selectable text was found. "
                    "Scanned PDFs are not supported."
                )

        except Exception as error:

            st.error(
                f"Could not read content file: {error}"
            )

            file_error = True
            content_text = ""

    if guideline_file is not None:

        try:
            guideline_text = extract_file_text(guideline_file)

            st.caption(
                f"Guideline source: {guideline_file.name}"
            )

            if guideline_text:

                with st.expander("Preview extracted guidelines"):
                    st.text(guideline_text[:3000])

            else:
                st.warning(
                    "No selectable guideline text was found."
                )

        except Exception as error:

            st.error(
                f"Could not read guideline file: {error}"
            )

            file_error = True
            guideline_text = ""

    st.caption(
        "Supported rules: Prohibited: term | "
        "Required: phrase | Fact: key = approved value"
    )

    st.divider()

    if st.button(
        "Run Brand Check",
        type="primary",
        use_container_width=True
    ):

        if asset_load_error:

            st.error(asset_load_error)

        elif asset_upload_incomplete:

            st.error(
                "Please upload both the approved reference image and the "
                "submitted image, or remove both to run text checks only."
            )

        elif file_error:

            st.error(
                "Fix the uploaded file issue before running the check."
            )

        elif not content_text.strip():

            st.error(
                "Please provide content to check."
            )

        elif not guideline_text.strip():

            st.error(
                "Please provide approved brand guidelines."
            )

        else:

            parsed, guideline_warnings = parse_guidelines(
                guideline_text
            )

            has_supported_rules = (
                bool(parsed["prohibited_terms"])
                or bool(parsed["required_phrases"])
                or bool(parsed["approved_facts"])
            )

            if not has_supported_rules:

                st.error(
                    "No supported rules were found. Use "
                    "'Prohibited: term', 'Required: phrase', "
                    "or 'Fact: key = approved value'."
                )

                st.session_state["guideline_warnings"] = (
                    guideline_warnings
                )

            else:

                try:

                    rule_guidelines = {
                        "prohibited_terms": parsed["prohibited_terms"],
                        "required_phrases": parsed["required_phrases"]
                    }

                    results = check_content(
                        content_text,
                        rule_guidelines
                    )

                    fact_results = check_approved_facts(
                        content_text,
                        parsed["approved_facts"]
                    )

                    results.extend(fact_results)

                    asset_summary = {
                        "status": "Skipped",
                        "message": "Asset comparison skipped because no image pair was provided.",
                        "approved_filename": "",
                        "submitted_filename": "",
                        "similarity_score": None,
                        "threshold": ASSET_SIMILARITY_THRESHOLD
                    }

                    if approved_asset_bytes and submitted_asset_bytes:

                        try:
                            comparison = compare_images(
                                approved_asset_bytes,
                                submitted_asset_bytes
                            )

                            similarity_score = comparison["similarity_score"]
                            possible_mismatch = not comparison["is_match"]

                            asset_summary = {
                                "status": (
                                    "Possible mismatch"
                                    if possible_mismatch
                                    else "Within threshold"
                                ),
                                "message": (
                                    f"Pixel similarity: {similarity_score:.2f}%. "
                                    f"Flag threshold: {comparison['threshold']:.2f}%."
                                ),
                                "approved_filename": approved_asset_name,
                                "submitted_filename": submitted_asset_name,
                                "similarity_score": similarity_score,
                                "threshold": comparison["threshold"],
                                "exact_match": comparison["exact_match"],
                                "mean_absolute_difference": comparison[
                                    "mean_absolute_difference"
                                ]
                            }

                            if possible_mismatch:
                                results.append({
                                    "type": "Brand Asset Mismatch",
                                    "severity": (
                                        "High" if similarity_score < 85.0 else "Medium"
                                    ),
                                    "message": (
                                        f"The submitted image has {similarity_score:.2f}% "
                                        f"pixel similarity to the approved reference, "
                                        f"below the {comparison['threshold']:.2f}% prototype "
                                        "threshold. Review the images manually."
                                    ),
                                    "evidence": (
                                        f"Approved: {approved_asset_name}; "
                                        f"Submitted: {submitted_asset_name}; "
                                        f"Pixel similarity: {similarity_score:.2f}%"
                                    ),
                                    "guideline": (
                                        "Compare the submitted image with the supplied "
                                        "approved reference asset. The configured prototype "
                                        f"threshold is {comparison['threshold']:.2f}%."
                                    ),
                                    "start": None,
                                    "end": None
                                })

                        except Exception as asset_error:
                            asset_summary = {
                                "status": "Error",
                                "message": f"Asset comparison failed: {asset_error}",
                                "approved_filename": approved_asset_name,
                                "submitted_filename": submitted_asset_name,
                                "similarity_score": None,
                                "threshold": ASSET_SIMILARITY_THRESHOLD
                            }

                    st.session_state["asset_check_summary"] = asset_summary
                    st.session_state["findings"] = results

                    st.session_state["review_status"] = {
                        index: "Pending"
                        for index in range(len(results))
                    }

                    st.session_state["last_content"] = content_text
                    st.session_state["last_guidelines"] = parsed

                    st.session_state["guideline_warnings"] = (
                        guideline_warnings
                    )

                    st.session_state["last_checked_at"] = (
                        datetime.now()
                        .astimezone()
                        .strftime("%d %b %Y, %I:%M %p")
                    )

                    st.session_state["checks_run"] += 1

                    st.success("Brand check completed.")

                except Exception as error:

                    st.error(
                        f"Brand check failed: {error}"
                    )

    # Guideline warnings remain visible after the check.

    if st.session_state["guideline_warnings"]:

        with st.expander(
            "View unsupported guideline instructions"
        ):

            for warning in st.session_state["guideline_warnings"]:
                st.warning(warning)

    findings = st.session_state["findings"]

    if findings is not None:

        st.divider()
        st.header("Checking Results")

        statuses = st.session_state["review_status"]

        confirmed = sum(
            statuses.get(i) == "Confirmed"
            for i in range(len(findings))
        )

        dismissed = sum(
            statuses.get(i) == "Dismissed"
            for i in range(len(findings))
        )

        pending = len(findings) - confirmed - dismissed

        metric1, metric2, metric3, metric4 = st.columns(4)

        metric1.metric("Total Issues", len(findings))
        metric2.metric("Confirmed", confirmed)
        metric3.metric("Dismissed", dismissed)
        metric4.metric("Pending", pending)

        st.caption(
            f"Last checked: {st.session_state['last_checked_at']}"
        )

        asset_summary = st.session_state.get("asset_check_summary")

        if asset_summary:

            st.subheader("Brand Asset Comparison")

            if asset_summary.get("status") == "Skipped":
                st.info(asset_summary.get("message", "Asset comparison was skipped."))

            elif asset_summary.get("status") == "Error":
                st.error(asset_summary.get("message", "Asset comparison failed."))

            else:
                asset_metric, threshold_metric = st.columns(2)

                asset_metric.metric(
                    "Pixel Similarity",
                    f"{asset_summary['similarity_score']:.2f}%"
                )

                threshold_metric.metric(
                    "Prototype Flag Threshold",
                    f"{asset_summary['threshold']:.2f}%"
                )

                st.caption(
                    f"Approved: {asset_summary['approved_filename']} | "
                    f"Submitted: {asset_summary['submitted_filename']}"
                )

                if asset_summary["status"] == "Possible mismatch":
                    st.warning(
                        "Possible visual mismatch detected. See the Brand Asset "
                        "Mismatch finding below and make a human decision."
                    )
                else:
                    st.success(
                        "No pixel mismatch above the configured threshold was detected. "
                        "This is not proof of brand approval or authenticity."
                    )

        if not findings:

            st.success(
                "No issues were detected by the configured checks. "
                "This does not guarantee full brand compliance."
            )

        else:

            st.subheader("Detected Issues")

            for index, finding in enumerate(findings):

                status = statuses.get(index, "Pending")

                with st.container(border=True):

                    title_col, severity_col = st.columns([3, 1])

                    with title_col:

                        st.markdown(
                            f"**{index + 1}. "
                            f"{finding.get('type', 'Finding')}**"
                        )

                    with severity_col:

                        st.caption(
                            f"Severity: {finding.get('severity', 'N/A')}"
                        )

                    st.write(
                        "Message:",
                        finding.get("message", "")
                    )

                    st.write(
                        "Evidence:",
                        finding.get("evidence", "")
                    )

                    st.write(
                        "Guideline:",
                        finding.get("guideline", "")
                    )

                    st.write(
                        f"Review Status: **{status}**"
                    )

                    confirm_col, dismiss_col = st.columns(2)

                    with confirm_col:

                        if st.button(
                            "Confirm Issue",
                            key=f"confirm_{index}",
                            use_container_width=True,
                            disabled=(status == "Confirmed")
                        ):

                            st.session_state["review_status"][index] = (
                                "Confirmed"
                            )

                            st.rerun()

                    with dismiss_col:

                        if st.button(
                            "False Positive",
                            key=f"dismiss_{index}",
                            use_container_width=True,
                            disabled=(status == "Dismissed")
                        ):

                            st.session_state["review_status"][index] = (
                                "Dismissed"
                            )

                            st.rerun()

        with st.expander(
            "View Original Content with Highlighted Findings"
        ):

            highlighted = make_highlighted_html(
                st.session_state["last_content"],
                findings
            )

            st.markdown(
                f'<div style="background:#111C33;padding:18px;'
                f'border:1px solid #263B60;border-radius:10px;'
                f'line-height:2;">{highlighted}</div>',
                unsafe_allow_html=True
            )

            st.caption(
                "Yellow highlights mark the text locations associated "
                "with findings. Fact-review findings highlight the "
                "sentence that needs checking."
            )

        st.divider()
        st.subheader("Download Review Report")

        report_txt = make_text_report(
            findings,
            statuses,
            st.session_state["last_checked_at"],
            st.session_state["guideline_warnings"],
            st.session_state.get("asset_check_summary")
        )

        report_csv = make_csv_report(
            findings,
            statuses,
            st.session_state.get("asset_check_summary")
        )

        download_left, download_right = st.columns(2)

        with download_left:

            st.download_button(
                "Download TXT Report",
                data=report_txt,
                file_name="KnowledgeBridge_Report.txt",
                mime="text/plain",
                use_container_width=True
            )

        with download_right:

            st.download_button(
                "Download CSV Report",
                data=report_csv,
                file_name="KnowledgeBridge_Report.csv",
                mime="text/csv",
                use_container_width=True
            )


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

elif page == "Dashboard":

    st.title("KnowledgeBridge Dashboard")

    st.markdown(
        '<p class="kb-subtitle">'
        'Overview of your brand governance checks and reviews.'
        '</p>',
        unsafe_allow_html=True
    )

    findings = st.session_state["findings"] or []
    statuses = st.session_state["review_status"]

    confirmed = sum(
        statuses.get(i) == "Confirmed"
        for i in range(len(findings))
    )

    dismissed = sum(
        statuses.get(i) == "Dismissed"
        for i in range(len(findings))
    )

    pending = len(findings) - confirmed - dismissed

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Checks Completed",
        st.session_state["checks_run"]
    )

    col2.metric(
        "Issues Detected",
        len(findings)
    )

    col3.metric(
        "Confirmed",
        confirmed
    )

    col4.metric(
        "Pending Review",
        pending
    )

    st.divider()

    st.subheader("Workflow")

    st.markdown("""
    1. Submit content by pasting text or uploading a TXT, PDF or DOCX file.
    2. Provide approved brand guidelines.
    3. Upload an approved image and submitted image, or use the included demo assets.
    4. Run the rule-based text checks and basic pixel-based asset comparison.
    5. Review prohibited terms, missing required phrases, approved-fact checks and possible asset mismatches.
    6. Confirm or dismiss detected findings; the human reviewer makes the final decision.
    7. Download a TXT or CSV review report containing findings and the asset-check summary.
    """)

    if st.session_state["last_checked_at"]:

        st.caption(
            f"Last check: {st.session_state['last_checked_at']}"
        )


# ---------------------------------------------------------
# ABOUT PAGE
# ---------------------------------------------------------

elif page == "About":

    st.title("About KnowledgeBridge")

    st.markdown(
        '<p class="kb-subtitle">'
        'A brand governance and content review assistant.'
        '</p>',
        unsafe_allow_html=True
    )

    st.divider()

    st.subheader("The Problem")

    st.write(
        "Organizations need to ensure submitted content follows "
        "approved brand terminology, required phrases and factual guidelines."
    )

    st.subheader("Our Solution")

    st.write(
        "KnowledgeBridge checks submitted content against supplied rules, "
        "identifies potential issues, shows evidence and lets a human "
        "reviewer make the final decision."
    )

    st.subheader("Current Prototype Features")

    st.markdown("""
    - TXT, PDF and DOCX text extraction.
    - Prohibited-term detection.
    - Missing required-phrase detection.
    - Approved-fact value comparison.
    - Warnings for unsupported guideline instructions.
    - Evidence and guideline explanations.
    - Human review: Confirm Issue or False Positive.
    - Highlighting detected text in submitted content.
    - Basic pixel-based comparison of approved and submitted image assets.
    - Human review for detected asset mismatches.
    - TXT and CSV report downloads including the asset-check summary.
    - Dashboard summary.
    """)

    st.subheader("Technology Stack")

    st.markdown("""
    - Python
    - Streamlit
    - Regular Expressions
    - Pillow (basic image normalization and pixel comparison)
    - PyPDF
    - python-docx
    """)

    st.info(
        "Approved-fact checking currently uses exact value matching "
        "within the same sentence as the fact key. It does not perform "
        "semantic AI analysis or external fact verification. Image checking "
        "uses normalized pixel differences and may be affected by resizing, "
        "compression, background or layout changes. It does not perform "
        "semantic image recognition or prove asset authenticity. Human "
        "reviewers remain responsible for final decisions."
    )

    st.divider()

    st.caption(
        "Developed by Team BUGBUSTERS | Asansol Engineering College"
    )
