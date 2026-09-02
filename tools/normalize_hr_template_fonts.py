"""Normalize the typography of supported HR templates.

The generator reads DOCX and ODT templates.  Updating the package XML directly
also covers text in tables, headers, footers, shapes, and inherited styles that
high-level document libraries can overlook.  Every template uses Poppins; the
new numbered templates additionally use a uniform 10-point font size.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "data" / "HR-files"
FONT = "Poppins"
NEW_TEMPLATE_SIZE_HALF_POINTS = b"20"
NEW_TEMPLATE_DRAWING_SIZE = b"1000"


def _set_xml_attribute(tag: bytes, attribute: bytes, value: bytes) -> bytes:
    pattern = re.compile(rb"\s+" + re.escape(attribute) + rb'="[^"]*"')
    replacement = b" " + attribute + b'="' + value + b'"'
    if pattern.search(tag):
        return pattern.sub(replacement, tag)
    return tag[:-2] + replacement + tag[-2:] if tag.endswith(b"/>") else tag[:-1] + replacement + b">"


def _normalize_docx_xml(name: str, data: bytes) -> bytes:
    if not name.endswith(".xml"):
        return data

    def update_rfonts(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        tag = re.sub(rb'\s+w:(?:asciiTheme|hAnsiTheme|eastAsiaTheme|cstheme)="[^"]*"', b"", tag)
        for attribute in (b"w:ascii", b"w:hAnsi", b"w:eastAsia", b"w:cs"):
            tag = _set_xml_attribute(tag, attribute, FONT.encode())
        return tag

    data = re.sub(rb"<w:rFonts\b[^>]*>", update_rfonts, data)

    def update_drawing_font(match: re.Match[bytes]) -> bytes:
        return _set_xml_attribute(match.group(0), b"typeface", FONT.encode())

    data = re.sub(rb"<a:(?:latin|ea|cs)\b[^>]*>", update_drawing_font, data)

    if name == "word/styles.xml":
        font_tag = (
            b'<w:rFonts w:ascii="Poppins" w:hAnsi="Poppins" '
            b'w:eastAsia="Poppins" w:cs="Poppins"/>'
        )
        if b"<w:rPrDefault" not in data:
            data = data.replace(b"<w:docDefaults>", b"<w:docDefaults><w:rPrDefault><w:rPr>" + font_tag + b"</w:rPr></w:rPrDefault>", 1)
        elif b"<w:rPrDefault/>" in data:
            data = data.replace(b"<w:rPrDefault/>", b"<w:rPrDefault><w:rPr>" + font_tag + b"</w:rPr></w:rPrDefault>", 1)
        else:
            start = data.find(b"<w:rPrDefault")
            end = data.find(b"</w:rPrDefault>", start)
            section = data[start:end]
            if b"<w:rFonts" not in section:
                if b"<w:rPr>" in section:
                    data = data[:start] + section.replace(b"<w:rPr>", b"<w:rPr>" + font_tag, 1) + data[end:]
                elif b"<w:rPr/>" in section:
                    data = data[:start] + section.replace(b"<w:rPr/>", b"<w:rPr>" + font_tag + b"</w:rPr>", 1) + data[end:]
    return data


def _normalize_numbered_docx_size(name: str, data: bytes) -> bytes:
    if not name.endswith(".xml"):
        return data

    def update_word_size(match: re.Match[bytes]) -> bytes:
        return _set_xml_attribute(match.group(0), b"w:val", NEW_TEMPLATE_SIZE_HALF_POINTS)

    data = re.sub(rb"<w:(?:sz|szCs)\b[^>]*>", update_word_size, data)

    def update_drawing_size(match: re.Match[bytes]) -> bytes:
        return _set_xml_attribute(match.group(0), b"sz", NEW_TEMPLATE_DRAWING_SIZE)

    data = re.sub(rb"<a:(?:defRPr|rPr|endParaRPr)\b[^>]*>", update_drawing_size, data)

    if name == "word/styles.xml":
        start = data.find(b"<w:rPrDefault")
        end = data.find(b"</w:rPrDefault>", start)
        if start >= 0 and end >= 0:
            section = data[start:end]
            additions = b""
            if not re.search(rb"<w:sz\b", section):
                additions += b'<w:sz w:val="20"/>'
            if not re.search(rb"<w:szCs\b", section):
                additions += b'<w:szCs w:val="20"/>'
            if additions:
                section = section.replace(b"<w:rPr>", b"<w:rPr>" + additions, 1)
                data = data[:start] + section + data[end:]
    return data


def _normalize_odt_xml(name: str, data: bytes) -> bytes:
    if name not in {"content.xml", "styles.xml"}:
        return data

    def update_text_properties(match: re.Match[bytes]) -> bytes:
        tag = match.group(0)
        for attribute in (
            b"style:font-name",
            b"style:font-name-asian",
            b"style:font-name-complex",
            b"fo:font-family",
        ):
            tag = _set_xml_attribute(tag, attribute, FONT.encode())
        return tag

    return re.sub(rb"<style:text-properties\b[^>]*>", update_text_properties, data)


def _rewrite_package(path: Path, normalizer) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=path.suffix, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
            for item in source.infolist():
                payload = normalizer(item.filename, source.read(item.filename))
                target.writestr(item, payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate(templates: list[Path]) -> None:
    expected = FONT.encode()
    for path in templates:
        with zipfile.ZipFile(path, "r") as package:
            damaged_entry = package.testzip()
            if damaged_entry:
                raise ValueError(f"Damaged ZIP entry in {path.name}: {damaged_entry}")
            for item in package.infolist():
                if not item.filename.endswith(".xml"):
                    continue
                data = package.read(item.filename)
                if path.suffix.lower() == ".docx":
                    for tag in re.findall(rb"<w:rFonts\b[^>]*>", data):
                        if any(
                            not re.search(rb"\s+" + attribute + rb'="' + expected + rb'"', tag)
                            for attribute in (b"w:ascii", b"w:hAnsi", b"w:eastAsia", b"w:cs")
                        ):
                            raise ValueError(f"Non-Poppins run font in {path.name}")
                        if re.search(rb"\s+w:(?:asciiTheme|hAnsiTheme|eastAsiaTheme|cstheme)=", tag):
                            raise ValueError(f"Theme font override in {path.name}")
                    for tag in re.findall(rb"<a:(?:latin|ea|cs)\b[^>]*>", data):
                        if not re.search(rb'\s+typeface="Poppins"', tag):
                            raise ValueError(f"Non-Poppins drawing font in {path.name}")
                    if re.match(r"^\d+\.", path.name):
                        for tag in re.findall(rb"<w:(?:sz|szCs)\b[^>]*>", data):
                            if not re.search(rb'\s+w:val="20"', tag):
                                raise ValueError(f"Non-10-point Word text in {path.name}")
                        for tag in re.findall(rb"<a:(?:defRPr|rPr|endParaRPr)\b[^>]*>", data):
                            if not re.search(rb'\s+sz="1000"', tag):
                                raise ValueError(f"Non-10-point drawing text in {path.name}")
                        if item.filename == "word/styles.xml":
                            start = data.find(b"<w:rPrDefault")
                            end = data.find(b"</w:rPrDefault>", start)
                            default = data[start:end]
                            if not re.search(rb'<w:sz\b[^>]*\s+w:val="20"', default) or not re.search(
                                rb'<w:szCs\b[^>]*\s+w:val="20"', default
                            ):
                                raise ValueError(f"Non-10-point default style in {path.name}")
                elif item.filename in {"content.xml", "styles.xml"}:
                    for tag in re.findall(rb"<style:text-properties\b[^>]*>", data):
                        if any(
                            not re.search(rb"\s+" + attribute + rb'="' + expected + rb'"', tag)
                            for attribute in (
                                b"style:font-name",
                                b"style:font-name-asian",
                                b"style:font-name-complex",
                                b"fo:font-family",
                            )
                        ):
                            raise ValueError(f"Non-Poppins ODT style in {path.name}")


def main() -> None:
    templates = sorted(TEMPLATE_DIR.glob("*.docx")) + sorted(TEMPLATE_DIR.glob("*.odt"))
    for path in templates:
        if path.suffix.lower() == ".docx":
            def normalize(name: str, data: bytes, *, numbered=bool(re.match(r"^\d+\.", path.name))) -> bytes:
                data = _normalize_docx_xml(name, data)
                return _normalize_numbered_docx_size(name, data) if numbered else data

            _rewrite_package(path, normalize)
        else:
            _rewrite_package(path, _normalize_odt_xml)
    _validate(templates)
    print(f"Normalized {len(templates)} templates to {FONT}.")


if __name__ == "__main__":
    main()
