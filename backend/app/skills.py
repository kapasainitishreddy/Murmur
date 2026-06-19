from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


def sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", text) if item.strip()]


def find_dates(text: str) -> list[str]:
    patterns = [
        r"\b(?:today|tomorrow|yesterday|tonight|next\s+\w+|this\s+\w+)\b",
        r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.I))
    return list(dict.fromkeys(found))


def find_actions(text: str) -> list[str]:
    verbs = r"(?:call|email|send|buy|replace|repair|check|follow up|schedule|create|update|submit|return|ask|remind|order|finish|review|contact)"
    output = []
    for sentence in sentences(text):
        if re.search(rf"\b{verbs}\b", sentence, flags=re.I):
            output.append(sentence)
    return output


def find_people(text: str) -> list[str]:
    names = re.findall(r"\b(?:with|from|to|by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text)
    return list(dict.fromkeys(names))


def base_result(text: str) -> dict[str, Any]:
    return {
        "summary": sentences(text)[0] if sentences(text) else text.strip(),
        "actions": find_actions(text),
        "dates": find_dates(text),
        "people": find_people(text),
    }


def memory(text: str) -> dict[str, Any]:
    result = base_result(text)
    location = re.search(r"\b(?:in|inside|under|above|behind|beside|near|on)\s+(.+?)(?:[.!?]|$)", text, re.I)
    result.update({"kind": "memory", "location": location.group(1).strip() if location else None})
    return result


def decision(text: str) -> dict[str, Any]:
    result = base_result(text)
    why = re.search(r"\b(?:because|since|so that)\s+(.+?)(?:[.!?]|$)", text, re.I)
    reconsider = re.search(r"\b(?:unless|reconsider if|change if)\s+(.+?)(?:[.!?]|$)", text, re.I)
    result.update({"kind": "decision_receipt", "reason": why.group(1).strip() if why else None, "reconsider_if": reconsider.group(1).strip() if reconsider else None})
    return result


def bug_report(text: str) -> dict[str, Any]:
    result = base_result(text)
    steps = [s for s in sentences(text) if re.search(r"\b(?:when|after|before|then|click|tap|open|select|enter)\b", s, re.I)]
    expected = re.search(r"\bexpected(?:ly)?\s+(?:to|that)?\s*(.+?)(?:[.!?]|$)", text, re.I)
    actual = re.search(r"\b(?:but|instead|actually)\s+(.+?)(?:[.!?]|$)", text, re.I)
    result.update({"kind": "bug_report", "reproduction_steps": steps, "expected": expected.group(1).strip() if expected else None, "actual": actual.group(1).strip() if actual else None, "severity": "high" if re.search(r"crash|data loss|payment|security", text, re.I) else "normal"})
    return result


def inspection(text: str) -> dict[str, Any]:
    result = base_result(text)
    issues = [s for s in sentences(text) if re.search(r"damage|crack|stain|leak|broken|missing|scratch|mold|dent", s, re.I)]
    rooms = re.findall(r"\b(?:kitchen|bedroom|bathroom|living room|garage|hallway|basement|roof|office)\b", text, re.I)
    result.update({"kind": "inspection", "issues": issues, "areas": list(dict.fromkeys(r.lower() for r in rooms))})
    return result


def care_log(text: str) -> dict[str, Any]:
    result = base_result(text)
    symptoms = [s for s in sentences(text) if re.search(r"pain|tired|scratch|itch|fever|cough|ate|drink|sleep|medicine|dose|vomit", s, re.I)]
    result.update({"kind": "care_log", "observations": symptoms, "medical_disclaimer": "Organizational note only; not a diagnosis."})
    return result


def inventory(text: str) -> dict[str, Any]:
    result = base_result(text)
    quantities = re.findall(r"\b(\d+)\s+([a-zA-Z][a-zA-Z -]{1,40}?)(?=,|\.| and |$)", text)
    result.update({"kind": "inventory", "items": [{"quantity": int(q), "item": name.strip()} for q, name in quantities]})
    return result


def sop(text: str) -> dict[str, Any]:
    result = base_result(text)
    result.update({"kind": "sop", "steps": [{"order": index + 1, "instruction": item} for index, item in enumerate(sentences(text))]})
    return result


def complaint(text: str) -> dict[str, Any]:
    result = base_result(text)
    resolution = re.search(r"\b(?:I want|I need|resolve by|resolution)\s+(.+?)(?:[.!?]|$)", text, re.I)
    result.update({"kind": "complaint", "timeline": sentences(text), "desired_resolution": resolution.group(1).strip() if resolution else None})
    return result


def dream(text: str) -> dict[str, Any]:
    result = base_result(text)
    emotions = re.findall(r"\b(?:happy|sad|afraid|scared|angry|calm|confused|excited|anxious|peaceful)\b", text, re.I)
    result.update({"kind": "dream", "emotions": list(dict.fromkeys(e.lower() for e in emotions)), "scenes": sentences(text)})
    return result


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    keywords: tuple[str, ...]
    processor: Callable[[str], dict[str, Any]]


SKILLS = [
    Skill("memory", "Memory", "Remember where things are and what happened.", ("remember", "kept", "left", "passport", "where"), memory),
    Skill("decision", "Decision Receipt", "Record a decision, reason, and reconsideration trigger.", ("decided", "decision", "because", "reconsider"), decision),
    Skill("bug", "Bug Report", "Create reproducible software issue reports.", ("bug", "error", "crash", "freeze", "button"), bug_report),
    Skill("inspection", "Inspection", "Structure property and equipment observations.", ("inspection", "damage", "crack", "leak", "stain"), inspection),
    Skill("care", "Care Log", "Organize pet, health, and caregiver observations.", ("pet", "vet", "doctor", "medicine", "pain", "ate"), care_log),
    Skill("inventory", "Inventory", "Extract quantities and stock observations.", ("inventory", "stock", "remaining", "boxes", "shirts"), inventory),
    Skill("sop", "SOP Builder", "Convert narrated work into ordered instructions.", ("first", "next", "then", "procedure", "sop"), sop),
    Skill("complaint", "Complaint Builder", "Create a timeline and requested resolution.", ("complaint", "refund", "charged", "landlord", "airline"), complaint),
    Skill("dream", "Dream Journal", "Preserve scenes, emotions, and recurring details.", ("dream", "woke", "sleep", "nightmare"), dream),
]


def choose_skill(text: str, requested: str | None = None) -> Skill:
    if requested:
        for skill in SKILLS:
            if skill.id == requested:
                return skill
    lowered = text.lower()
    scored = [(sum(1 for keyword in skill.keywords if keyword in lowered), skill) for skill in SKILLS]
    score, skill = max(scored, key=lambda item: item[0])
    return skill if score else SKILLS[0]


def process_with_skill(text: str, requested: str | None = None) -> dict[str, Any]:
    skill = choose_skill(text, requested)
    return {"skill": {"id": skill.id, "name": skill.name}, "result": skill.processor(text)}


def skill_catalog() -> list[dict[str, str]]:
    return [{"id": skill.id, "name": skill.name, "description": skill.description} for skill in SKILLS]
