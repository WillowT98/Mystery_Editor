from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
import xml.etree.ElementTree as ET


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class LocalizationEntry:
    key: str
    source: str
    context: str

    @property
    def hash(self) -> str:
        return source_hash(self.source)


@dataclass(frozen=True)
class TranslationRecord:
    text: str
    source_hash: str


class ProjectLocalization:
    """Project-local translation storage and interchange.

    Source-language strings remain in their normal content files so authors edit
    them in context. Locale files contain only translations plus the hash of the
    source text they were translated from. That makes stale translations
    detectable without coupling game logic to human-readable text.
    """

    def __init__(
        self,
        root: Path,
        *,
        source_locale: str = "en-US",
        default_locale: str | None = None,
        supported_locales: Iterable[str] = (),
        locale_names: dict[str, str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.source_locale = source_locale or "en-US"
        self.default_locale = default_locale or self.source_locale
        supported = [self.source_locale]
        for locale in supported_locales:
            locale = str(locale).strip()
            if locale and locale not in supported:
                supported.append(locale)
        if self.default_locale not in supported:
            supported.append(self.default_locale)
        self.supported_locales = supported
        self.locale_names = dict(locale_names or {})
        self.active_locale = self.source_locale
        self._cache: dict[str, dict[str, TranslationRecord]] = {}

    def locale_label(self, locale: str) -> str:
        return self.locale_names.get(locale, locale)

    def locale_path(self, locale: str) -> Path:
        return self.root / f"{locale}.json"

    def set_active_locale(self, locale: str | None) -> str:
        requested = (locale or self.default_locale or self.source_locale).strip()
        if requested not in self.supported_locales:
            # If a regional locale is requested and its base language is a
            # configured locale, use that before falling back to the source.
            base = requested.split("-", 1)[0]
            requested = next(
                (value for value in self.supported_locales if value == base),
                self.source_locale,
            )
        self.active_locale = requested
        return requested

    def load_locale(self, locale: str) -> dict[str, TranslationRecord]:
        if locale == self.source_locale:
            return {}
        if locale in self._cache:
            return self._cache[locale]
        path = self.locale_path(locale)
        records: dict[str, TranslationRecord] = {}
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = dict(payload.get("translations", {})) if isinstance(payload, dict) else {}
            for key, value in raw.items():
                if isinstance(value, str):
                    records[str(key)] = TranslationRecord(value, "")
                elif isinstance(value, dict):
                    records[str(key)] = TranslationRecord(
                        str(value.get("text", "")),
                        str(value.get("source_hash", "")),
                    )
        self._cache[locale] = records
        return records

    def save_locale(self, locale: str, records: dict[str, TranslationRecord] | None = None) -> Path:
        if locale == self.source_locale:
            raise ValueError("Source-language text lives in project content, not a locale override file.")
        records = records if records is not None else self.load_locale(locale)
        path = self.locale_path(locale)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": 1,
            "locale": locale,
            "translations": {
                key: {"text": value.text, "source_hash": value.source_hash}
                for key, value in sorted(records.items())
                if value.text
            },
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self._cache[locale] = dict(records)
        return path

    def has_translations(self) -> bool:
        for locale in self.supported_locales:
            if locale == self.source_locale:
                continue
            if any(record.text for record in self.load_locale(locale).values()):
                return True
        return False

    def add_locale(self, locale: str, label: str | None = None) -> None:
        locale = locale.strip()
        if not locale:
            raise ValueError("Locale code cannot be blank.")
        if locale not in self.supported_locales:
            self.supported_locales.append(locale)
        if label and label.strip():
            self.locale_names[locale] = label.strip()
        if locale != self.source_locale and not self.locale_path(locale).exists():
            self.save_locale(locale, {})

    def remove_locale(self, locale: str) -> None:
        if locale == self.source_locale:
            raise ValueError("The source locale cannot be removed.")
        self.supported_locales = [value for value in self.supported_locales if value != locale]
        self.locale_names.pop(locale, None)
        if self.default_locale == locale:
            self.default_locale = self.source_locale
        if self.active_locale == locale:
            self.active_locale = self.source_locale
        self._cache.pop(locale, None)

    def status(self, entry: LocalizationEntry, locale: str) -> str:
        if locale == self.source_locale:
            return "source"
        record = self.load_locale(locale).get(entry.key)
        if record is None or not record.text:
            return "missing"
        if record.source_hash != entry.hash:
            return "stale"
        return "translated"

    def coverage(self, entries: Iterable[LocalizationEntry], locale: str) -> tuple[int, int, int]:
        material = [entry for entry in entries if entry.source]
        if locale == self.source_locale:
            return len(material), 0, len(material)
        translated = 0
        stale = 0
        for entry in material:
            status = self.status(entry, locale)
            if status == "translated":
                translated += 1
            elif status == "stale":
                stale += 1
        return translated, stale, len(material)

    def translate(
        self,
        key: str,
        source: str,
        *,
        locale: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> str:
        locale = locale or self.active_locale
        text = source
        if locale != self.source_locale:
            record = self.load_locale(locale).get(key)
            if record is not None and record.text:
                text = record.text
        if variables:
            class SafeDict(dict):
                def __missing__(self, missing):
                    return "{" + str(missing) + "}"
            try:
                text = text.format_map(SafeDict(variables))
            except (ValueError, KeyError):
                pass
        return text

    def set_translation(
        self,
        locale: str,
        entry: LocalizationEntry,
        text: str,
        *,
        translated_source_hash: str | None = None,
    ) -> None:
        if locale == self.source_locale:
            raise ValueError("Edit source-language text in its normal project editor.")
        records = self.load_locale(locale)
        cleaned = text.rstrip()
        if cleaned:
            records[entry.key] = TranslationRecord(
                cleaned,
                translated_source_hash or entry.hash,
            )
        else:
            records.pop(entry.key, None)
        self.save_locale(locale, records)

    def export_csv(self, path: Path, locale: str, entries: Iterable[LocalizationEntry]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        records = self.load_locale(locale)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["key", "context", "source", "source_hash", "translation", "status"],
            )
            writer.writeheader()
            for entry in entries:
                record = records.get(entry.key)
                writer.writerow({
                    "key": entry.key,
                    "context": entry.context,
                    "source": entry.source,
                    "source_hash": entry.hash,
                    "translation": record.text if record else "",
                    "status": self.status(entry, locale),
                })
        return path

    def import_csv(self, path: Path, locale: str, entries: Iterable[LocalizationEntry]) -> tuple[int, int]:
        by_key = {entry.key: entry for entry in entries}
        records = self.load_locale(locale)
        imported = skipped = 0
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                key = str(row.get("key", "")).strip()
                entry = by_key.get(key)
                translation = str(row.get("translation", "")).rstrip()
                if entry is None or not translation:
                    skipped += 1
                    continue
                records[key] = TranslationRecord(
                    translation,
                    str(row.get("source_hash", "")).strip() or entry.hash,
                )
                imported += 1
        self.save_locale(locale, records)
        return imported, skipped

    def export_xliff(self, path: Path, locale: str, entries: Iterable[LocalizationEntry]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        xliff = ET.Element("xliff", {"version": "1.2"})
        file_node = ET.SubElement(xliff, "file", {
            "source-language": self.source_locale,
            "target-language": locale,
            "datatype": "plaintext",
            "original": "mystery-engine-project",
        })
        body = ET.SubElement(file_node, "body")
        records = self.load_locale(locale)
        for entry in entries:
            unit = ET.SubElement(body, "trans-unit", {"id": entry.key, "resname": entry.key})
            ET.SubElement(unit, "source").text = entry.source
            record = records.get(entry.key)
            target = ET.SubElement(unit, "target")
            target.text = record.text if record else ""
            if record:
                target.set("state", "translated" if record.source_hash == entry.hash else "needs-review-translation")
            context_group = ET.SubElement(unit, "context-group", {"purpose": "information"})
            ET.SubElement(context_group, "context", {"context-type": "x-context"}).text = entry.context
            ET.SubElement(context_group, "context", {"context-type": "x-source-hash"}).text = entry.hash
        tree = ET.ElementTree(xliff)
        try:
            ET.indent(tree, space="  ")
        except AttributeError:
            pass
        tree.write(path, encoding="utf-8", xml_declaration=True)
        return path

    def import_xliff(self, path: Path, locale: str, entries: Iterable[LocalizationEntry]) -> tuple[int, int]:
        by_key = {entry.key: entry for entry in entries}
        records = self.load_locale(locale)
        imported = skipped = 0
        root = ET.parse(path).getroot()

        def local_name(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        for unit in (node for node in root.iter() if local_name(node.tag) == "trans-unit"):
            key = str(unit.attrib.get("resname") or unit.attrib.get("id") or "")
            entry = by_key.get(key)
            if entry is None:
                skipped += 1
                continue
            target = next((child for child in unit if local_name(child.tag) == "target"), None)
            text = "" if target is None else "".join(target.itertext()).rstrip()
            if not text:
                skipped += 1
                continue
            exported_hash = ""
            for child in unit.iter():
                if local_name(child.tag) == "context" and child.attrib.get("context-type") == "x-source-hash":
                    exported_hash = (child.text or "").strip()
                    break
            records[key] = TranslationRecord(text, exported_hash or entry.hash)
            imported += 1
        self.save_locale(locale, records)
        return imported, skipped
