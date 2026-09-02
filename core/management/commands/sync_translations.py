"""Fill the .po catalogues from the editable sources in ``locale/_source``.

Source strings are authored in English. Turkish comes from
``locale/_source/tr.py``; the English catalogue is filled with the source
strings themselves so it always wins over any third-party catalogue.
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

ENTRY_RE = re.compile(
    r'(?P<prefix>(?:^#.*\n)*)msgid (?P<msgid>(?:".*"\n)+)msgstr (?P<msgstr>(?:".*"\n?)+)',
    re.M,
)


def unquote(block: str) -> str:
    """Join a multi-line PO string into the Python value it represents."""
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', block)
    joined = "".join(parts)
    return joined.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    )
    lines = escaped.split("\n")
    if len(lines) == 1:
        return f'"{escaped}"\n'
    out = ['""\n']
    for index, line in enumerate(lines):
        suffix = "\\n" if index < len(lines) - 1 else ""
        out.append(f'"{line}{suffix}"\n')
    return "".join(out)


def strip_fuzzy(prefix: str) -> str:
    """Drop the fuzzy marker from an entry's comment block.

    ``makemessages`` marks a new string fuzzy when it resembles an existing
    one, and ``msgfmt`` silently leaves fuzzy entries out of the compiled
    catalogue - the translation would sit in the .po file and never reach a
    page. Since we are writing the real translation here, the guess markers go.
    """
    lines = []
    for line in prefix.splitlines():
        if line.startswith("#|"):  # "previous msgid" hint
            continue
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",") if f.strip() != "fuzzy"]
            if not flags:
                continue
            line = "#, " + ", ".join(flags)
        lines.append(line)
    return "".join(f"{line}\n" for line in lines)


class Command(BaseCommand):
    help = "Writes the translations from locale/_source into the .po catalogues."

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-missing", action="store_true",
            help="List source strings that have no Turkish translation yet.",
        )

    HEADER_FIELDS = {
        "tr": ("Turkish", "nplurals=2; plural=(n != 1);"),
        "en": ("English", "nplurals=2; plural=(n != 1);"),
    }

    def fix_header(self, content: str, language: str) -> str:
        """Replace the placeholder header makemessages writes."""
        name, plural = self.HEADER_FIELDS[language]
        content = content.replace("#, fuzzy\n", "", 1)
        content = content.replace(
            '"Project-Id-Version: PACKAGE VERSION\\n"',
            '"Project-Id-Version: Dealer Order Management System\\n"',
        )
        content = content.replace(
            '"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"',
            '"Last-Translator: \\n"',
        )
        content = content.replace(
            '"Language-Team: LANGUAGE <LL@li.org>\\n"',
            f'"Language-Team: {name}\\n"',
        )
        content = content.replace('"Language: \\n"', f'"Language: {language}\\n"')
        content = re.sub(
            r'"Plural-Forms: [^"]*"',
            lambda _match: '"Plural-Forms: ' + plural + '\\n"',
            content,
        )
        return content

    def handle(self, *args, **options):
        base = Path(settings.BASE_DIR)
        namespace: dict = {}
        source = (base / "locale" / "_source" / "tr.py").read_text(encoding="utf-8")
        exec(compile(source, "tr.py", "exec"), namespace)
        turkish = namespace["TRANSLATIONS"]

        missing = []
        for language in ("tr", "en"):
            path = base / "locale" / language / "LC_MESSAGES" / "django.po"
            if not path.exists():
                self.stderr.write(f"{path} not found; run makemessages first.")
                continue
            content = path.read_text(encoding="utf-8")
            filled = 0

            def replace(match):
                nonlocal filled
                msgid = unquote(match.group("msgid"))
                if not msgid:  # the catalogue header
                    return match.group(0)
                if language == "tr":
                    value = turkish.get(msgid)
                    if value is None:
                        missing.append(msgid)
                        return match.group(0)
                else:
                    value = msgid
                filled += 1
                prefix = strip_fuzzy(match.group("prefix"))
                return f'{prefix}msgid {match.group("msgid")}msgstr {quote(value)}'

            content = ENTRY_RE.sub(replace, content)
            content = self.fix_header(content, language)
            path.write_text(content, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"{language}: {filled} entries written"))

        if missing:
            self.stdout.write(
                self.style.WARNING(f"{len(missing)} Turkish translations are missing:")
            )
            for item in sorted(set(missing)):
                self.stdout.write(f"  - {item}")
        elif options["report_missing"]:
            self.stdout.write(self.style.SUCCESS("No missing Turkish translations."))
