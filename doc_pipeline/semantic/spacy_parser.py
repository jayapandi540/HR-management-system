import re
def mask_pii_in_text(text: str):
    """Simple regex-based PII masking."""
    pii = {}
    # Email
    email_pattern = r'\b[\w\.-]+@[\w\.-]+\.\w+\b'
    emails = re.findall(email_pattern, text)
    if emails:
        pii['email'] = emails[0]
        text = re.sub(email_pattern, '[EMAIL]', text)
    # Phone
    phone_pattern = r'\b\d{10,15}\b'
    phones = re.findall(phone_pattern, text)
    if phones:
        pii['phone'] = phones[0]
        text = re.sub(phone_pattern, '[PHONE]', text)
    return text, pii