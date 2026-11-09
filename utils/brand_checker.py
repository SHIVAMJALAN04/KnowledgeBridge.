import re


def check_content(content: str, guidelines: dict) -> list:
    findings = []

    if not content or not content.strip():
        return findings

    # Check prohibited terms
    for term in guidelines.get("prohibited_terms", []):

        if not isinstance(term, str) or not term.strip():
            continue

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

    # Check required phrases
    for phrase in guidelines.get("required_phrases", []):

        if not isinstance(phrase, str) or not phrase.strip():
            continue

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