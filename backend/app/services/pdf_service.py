import markdown
from weasyprint import HTML


def markdown_to_pdf_bytes(md_content: str) -> bytes:
    html_body = markdown.markdown(md_content, extensions=["tables"])
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Noto Sans KR', sans-serif; margin: 40px; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  th {{ background: #f5f5f5; }}
  h1, h2, h3 {{ color: #1a1a2e; }}
</style>
</head>
<body>{html_body}</body>
</html>"""
    return HTML(string=full_html).write_pdf()
