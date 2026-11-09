# KnowledgeBridge
### Brand Governance & Content Review System

**Team:** BUGBUSTERS  
**Institution:** Asansol Engineering College  
**Hackathon:** CoderInPune – Round 2

## 1. Project Overview

KnowledgeBridge is a brand governance and content review application designed to help teams check submitted content against approved brand guidelines.

It identifies potential guideline violations, highlights missing required phrases, flags approved-fact discrepancies, and compares submitted brand assets against approved reference images.

The application presents findings for human review. The final decision remains with the reviewer.

## 2. Problem Statement

Organizations and teams need to ensure that their published content follows approved brand guidelines.

Manually checking content can make it difficult to consistently identify prohibited terms, missing required phrases, incorrect approved facts, and modified brand assets.

KnowledgeBridge provides a single interface to assist with these checks and organize the review process.

## 3. Key Features

### Content and Guideline Upload
- Upload content in TXT, PDF, and DOCX formats.
- Upload brand guidelines in TXT, PDF, and DOCX formats.

### Prohibited Term Detection
- Detects prohibited terms defined in the guidelines.
- Highlights matching terms in submitted content.

### Required Phrase Checking
- Checks whether required phrases appear in the submitted content.
- Flags missing required phrases.

### Approved Fact Review
- Checks approved facts against submitted content.
- Flags possible discrepancies for human review.

### Brand Asset Comparison
- Upload an approved reference image and a submitted image.
- Calculates basic pixel-based similarity.
- Flags images with similarity below the configured 95% threshold.

### Human Review
- Review detected findings.
- Confirm or dismiss individual findings.
- Track review statuses.

### Reports
- Export review findings and statuses in TXT and CSV formats.

### Dashboard
- View review information and navigate between the application's sections.

## 4. Application Workflow

1. Upload the content that needs to be reviewed.
2. Upload the approved brand guidelines.
3. The application processes the content and checks it against the guidelines.
4. Review detected issues and supporting evidence.
5. Compare submitted brand assets with approved reference images when required.
6. A human reviewer confirms or dismisses the findings.
7. Export the review report.

## 5. Guideline Format

The application supports the following guideline format:

```text
Prohibited: guaranteed
Required: Terms and conditions apply
Fact: warranty = 2 years
Fact: founded = 2015
```

- `Prohibited:` defines a term that should not appear.
- `Required:` defines a phrase that must appear.
- `Fact:` defines an approved fact and its expected value.

## 6. Technology Stack

- **Programming Language:** Python
- **Application Framework:** Streamlit
- **Image Processing:** Pillow (PIL)
- **PDF Processing:** pypdf
- **DOCX Processing:** python-docx

## 7. Project Structure

```text
KnowledgeBridge/
│
├── app.py
├── requirements.txt
├── README.md
├── STEP1_SETUP.txt
│
├── assets/
│   ├── demo_approved_logo.png
│   └── demo_modified_logo.png
│
├── components/
│   ├── dashboard.py
│   ├── upload.py
│   └── results.py
│
├── sample_data/
│
├── tests/
│   └── test_asset_checker.py
│
└── utils/
    ├── __init__.py
    ├── asset_checker.py
    ├── brand_checker.py
    └── helpers.py
```

## 8. Installation and Setup

### Step 1: Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
```

### Step 2: Open the project directory

```bash
cd KnowledgeBridge
```

### Step 3: Create a virtual environment

```bash
python -m venv .venv
```

### Step 4: Activate the environment (Windows PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
```

### Step 5: Install dependencies

```bash
python -m pip install -r requirements.txt
```

### Step 6: Run the application

```bash
python -m streamlit run app.py
```

The application will open in your browser.

## 9. Current Limitations

- Approved fact checking uses exact value matching within the relevant sentence. It does not perform semantic AI-based fact verification or verify facts against external sources.
- Brand asset checking uses basic pixel similarity. It does not establish logo authenticity or trademark ownership.
- Image resizing, compression, or background changes can affect similarity scores.
- Detected issues require human review. The application does not make the final brand approval decision automatically.

## 10. Team

**BUGBUSTERS**

- Shammika Srivastava
- Shivam Jalan

**Institution:** Asansol Engineering College

## 11. Future Improvements

Potential improvements include:

- Versioned brand workspaces.
- Deeper contextual content validation.
- Review history and tracking.
- Integration with team review workflows.

## 12. Project Status

KnowledgeBridge is a hackathon prototype developed for the CoderInPune Round 2 brand governance and content review requirements.

Features and limitations are documented according to the current implementation.
