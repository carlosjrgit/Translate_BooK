"""Manual de estilo e diretrizes editoriais da obra (Style Bible).

Registra dimensões estilísticas com rastreamento estrito de evidências textuais,
confiança e suporte a travamento manual (locked), além de oferecer validadores
programáticos para o pipeline de Quality Assurance (QA).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from book_translator.logging import get_logger

logger = get_logger("memory.style_bible")

# Palavras de baixo calão comuns em inglês e equivalentes em português
ENGLISH_PROFANITIES = {
    "fuck": ["porra", "foder", "caralho", "merda"],
    "fucking": ["maldito", "porra", "fodido", "caralho"],
    "shit": ["merda", "bosta"],
    "bitch": ["cadela", "vadia", "puta"],
    "bastard": ["bastardo", "desgraçado", "maldito"],
    "asshole": ["babaca", "arrombado", "escroto"],
    "damn": ["droga", "maldito", "caramba"],
}

# Títulos comuns e traduções esperadas em PT-BR
NOBILITY_TITLES = {
    "lord": "lorde",
    "lady": "lady",
    "sir": "senhor",
    "count": "conde",
    "earl": "conde",
    "countess": "condessa",
    "duke": "duque",
    "duchess": "duquesa",
    "baron": "barão",
    "baroness": "baronesa",
    "marquess": "marquês",
    "marquis": "marquês",
    "viscount": "visconde",
    "king": "rei",
    "queen": "rainha",
    "prince": "príncipe",
    "princess": "princesa",
    "emperor": "imperador",
    "empress": "imperatriz",
    "knight": "cavaleiro",
}


@dataclass
class StyleEvidence:
    """Citação textual de evidência que ancora uma regra ou inferência de estilo."""

    snippet: str
    chapter_id: str = ""
    unit_id: str = ""
    location_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "snippet": self.snippet,
            "chapter_id": self.chapter_id,
            "unit_id": self.unit_id,
            "location_note": self.location_note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleEvidence:
        return cls(
            snippet=data.get("snippet", ""),
            chapter_id=data.get("chapter_id", ""),
            unit_id=data.get("unit_id", ""),
            location_note=data.get("location_note", ""),
        )


@dataclass
class StyleRule:
    """Regra ou diretriz de estilo com rastreabilidade de evidência, origem e confiança."""

    name: str = ""
    value: str = ""
    confidence: float = 1.0
    evidences: list[StyleEvidence] = field(default_factory=list)
    locked: bool = False
    notes: str = ""
    is_inferred: bool = False
    source_type: str = "explicit"  # 'explicit' ou 'inferred'
    source: str = ""  # capítulo, unidade, análise global ou usuário
    dimension: str = ""
    rule: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.name and self.dimension:
            self.name = self.dimension
        elif not self.dimension and self.name:
            self.dimension = self.name

        if not self.value and self.rule:
            self.value = self.rule
        elif not self.rule and self.value:
            self.rule = self.value

        if self.evidence:
            if not any(e.snippet == self.evidence for e in self.evidences):
                self.evidences.append(StyleEvidence(snippet=self.evidence))
        elif self.evidences and not self.evidence:
            self.evidence = self.evidences[0].snippet

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "confidence": self.confidence,
            "evidences": [e.to_dict() for e in self.evidences],
            "locked": self.locked,
            "notes": self.notes,
            "is_inferred": self.is_inferred,
            "source_type": self.source_type,
            "source": self.source,
            "dimension": self.dimension,
            "rule": self.rule,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleRule:
        evs = [
            StyleEvidence.from_dict(e) if isinstance(e, dict) else StyleEvidence(str(e))
            for e in data.get("evidences", [])
        ]
        is_inf = bool(data.get("is_inferred", False))
        source_type = data.get("source_type", "inferred" if is_inf else "explicit")
        return cls(
            name=data.get("name", data.get("dimension", "")),
            value=data.get("value", data.get("rule", "")),
            confidence=float(data.get("confidence", 1.0)),
            evidences=evs,
            locked=bool(data.get("locked", False)),
            notes=data.get("notes", ""),
            is_inferred=is_inf,
            source_type=source_type,
            source=data.get("source", ""),
            dimension=data.get("dimension", data.get("name", "")),
            rule=data.get("rule", data.get("value", "")),
            evidence=data.get("evidence", ""),
        )


@dataclass
class StyleViolation:
    """Registro de desconformidade estilística para o pipeline de QA."""

    rule_name: str
    severity: str  # 'error', 'warning', 'info'
    message: str
    snippet: str = ""
    suggested_fix: str = ""

    @property
    def dimension(self) -> str:
        if "profanity" in self.rule_name:
            return "profanity"
        return self.rule_name


@dataclass
class StyleBible:
    """Manual editorial e de estilo da obra com suporte a evidências e validação de QA."""

    # 10 Dimensões fundamentais
    narrator: str = "terceira pessoa"
    narrative_person: str = "terceira pessoa"
    predominant_tense: str = "passado"
    formality_level: str = "formal"
    dialogue_style: str = "travessão"
    profanity_handling: str = "preservar intensidade do original"
    treatment_forms: str = "você"
    editorial_punctuation: str = "editorial brasileiro"
    title_treatment: str = "traduzir"
    internal_conventions: list[str] = field(default_factory=list)

    # Campos de compatibilidade e metadados
    register: str = "literário contemporâneo"
    predominant_treatment: str = "você"
    punctuation_standard: str = "editorial brasileiro"
    project_id: Any = ""
    tone: str = "literário"
    custom_rules: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, StyleRule] = field(default_factory=dict)

    @property
    def formality(self) -> str:
        return self.formality_level

    @formality.setter
    def formality(self, val: str) -> None:
        self.formality_level = val
        self.register = val

    @property
    def profanity_policy(self) -> str:
        return self.profanity_handling

    @profanity_policy.setter
    def profanity_policy(self, val: str) -> None:
        self.profanity_handling = val

    def __post_init__(self) -> None:
        """Sincroniza campos canônicos e dicionário de regras estruturadas."""
        self._sync_core_rules()

    def _sync_core_rules(self) -> None:
        """Garante que as 10 dimensões fundamentais existam no dicionário de regras."""
        defaults = {
            "narrator": (self.narrator, "Narrador predominante da obra"),
            "narrative_person": (self.narrative_person, "Pessoa narrativa (1ª, 2ª, 3ª pessoa)"),
            "predominant_tense": (
                self.predominant_tense,
                "Tempo verbal predominante (passado, presente)",
            ),
            "formality_level": (self.formality_level, "Nível de formalidade do texto"),
            "dialogue_style": (self.dialogue_style, "Padrão de abertura e formatação de diálogos"),
            "profanity_handling": (
                self.profanity_handling,
                "Política de tratamento de termos de baixo calão",
            ),
            "treatment_forms": (
                self.treatment_forms,
                "Forma de tratamento predominante e pronominal",
            ),
            "editorial_punctuation": (self.editorial_punctuation, "Padrão de pontuação editorial"),
            "title_treatment": (self.title_treatment, "Tratamento de títulos de nobreza e cargos"),
            "internal_conventions": (
                ", ".join(self.internal_conventions) if self.internal_conventions else "padrão",
                "Convenções internas específicas",
            ),
        }
        for name, (val, notes) in defaults.items():
            if name not in self.rules:
                self.rules[name] = StyleRule(name=name, value=str(val), confidence=1.0, notes=notes)

    def set_rule(
        self,
        name_or_rule: str | StyleRule,
        value: str = "",
        confidence: float = 1.0,
        evidences: list[str | StyleEvidence] | None = None,
        locked: bool = False,
        notes: str = "",
        force: bool = False,
        is_inferred: bool = False,
        source_type: str | None = None,
        source: str = "",
        dimension: str = "",
        rule: str = "",
        evidence: str = "",
    ) -> bool:
        """Define ou atualiza uma regra de estilo.

        Suporta passagem de instância StyleRule ou argumentos individuais.
        Se a regra estiver travada (`locked=True`), retorna False sem force=True.
        """
        aliases_map = {
            "formality": "formality_level",
            "profanity": "profanity_handling",
            "profanity_policy": "profanity_handling",
            "punctuation": "editorial_punctuation",
            "punctuation_policy": "editorial_punctuation",
        }

        if isinstance(name_or_rule, StyleRule):
            r_obj = name_or_rule
            name = r_obj.name or r_obj.dimension
            value = r_obj.value or r_obj.rule
            confidence = r_obj.confidence
            evidences = list(r_obj.evidences)
            locked = r_obj.locked
            notes = r_obj.notes
            is_inferred = r_obj.is_inferred
            source_type = r_obj.source_type
            source = r_obj.source
        else:
            name = name_or_rule or dimension
            value = value or rule
            if evidence and not evidences:
                evidences = [StyleEvidence(snippet=evidence)]

        canonical_name = aliases_map.get(name, name)
        existing = self.rules.get(name) or self.rules.get(canonical_name)
        if existing and existing.locked and not force:
            return False

        processed_evidences: list[StyleEvidence] = []
        if evidences:
            for ev in evidences:
                if isinstance(ev, StyleEvidence):
                    processed_evidences.append(ev)
                else:
                    processed_evidences.append(StyleEvidence(snippet=str(ev)))
        elif existing:
            processed_evidences = list(existing.evidences)

        actual_source_type = source_type or ("inferred" if is_inferred else "explicit")
        if actual_source_type == "inferred":
            is_inferred = True

        rule_inst = StyleRule(
            name=name,
            value=value,
            confidence=confidence,
            evidences=processed_evidences,
            locked=locked or (existing.locked if existing else False),
            notes=notes or (existing.notes if existing else ""),
            is_inferred=is_inferred,
            source_type=actual_source_type,
            source=source or (existing.source if existing else ""),
            dimension=name,
            rule=value,
            evidence=processed_evidences[0].snippet if processed_evidences else "",
        )
        self.rules[name] = rule_inst
        if canonical_name != name:
            self.rules[canonical_name] = rule_inst

        # Sincroniza atributos diretos
        if name in ("narrator",):
            self.narrator = value
        elif name in ("narrative_person",):
            self.narrative_person = value
        elif name in ("predominant_tense",):
            self.predominant_tense = value
        elif name in ("formality", "formality_level"):
            self.formality_level = value
            self.register = value
        elif name in ("dialogue_style",):
            self.dialogue_style = value
        elif name in ("profanity", "profanity_policy", "profanity_handling"):
            self.profanity_handling = value
        elif name in ("treatment_forms", "treatment"):
            self.treatment_forms = value
            self.predominant_treatment = value
        elif name in ("punctuation", "punctuation_policy", "editorial_punctuation"):
            self.editorial_punctuation = value
            self.punctuation_standard = value
        elif name in ("title_treatment",):
            self.title_treatment = value
        elif name in ("internal_conventions",):
            self.internal_conventions = [v.strip() for v in value.split(",") if v.strip()]

        return True

    def get_rule(self, name: str) -> StyleRule | None:
        """Retorna uma regra de estilo estruturada, suportando sinônimos das dimensões."""
        aliases_map = {
            "formality": "formality_level",
            "profanity": "profanity_handling",
            "profanity_policy": "profanity_handling",
            "punctuation": "editorial_punctuation",
            "punctuation_policy": "editorial_punctuation",
        }
        if name in self.rules:
            return self.rules[name]
        canonical = aliases_map.get(name)
        if canonical and canonical in self.rules:
            return self.rules[canonical]
        for k, v in aliases_map.items():
            if v == name and k in self.rules:
                return self.rules[k]
        return None

    def add_evidence(
        self,
        name: str,
        snippet: str,
        chapter_id: str = "",
        unit_id: str = "",
        location_note: str = "",
    ) -> None:
        """Registra uma evidência textual para uma regra de estilo."""
        if name not in self.rules:
            self.set_rule(name=name, value="", confidence=1.0)
        self.rules[name].evidences.append(
            StyleEvidence(
                snippet=snippet,
                chapter_id=chapter_id,
                unit_id=unit_id,
                location_note=location_note,
            )
        )

    def lock_rule(self, name: str, locked: bool = True) -> None:
        """Trava ou destrava uma regra de estilo."""
        if name in self.rules:
            self.rules[name].locked = locked

    def to_dict(self) -> dict[str, Any]:
        """Serializa a Style Bible completa em formato JSON/dict."""
        return {
            "narrator": self.narrator,
            "narrative_person": self.narrative_person,
            "predominant_tense": self.predominant_tense,
            "formality_level": self.formality_level,
            "dialogue_style": self.dialogue_style,
            "profanity_handling": self.profanity_handling,
            "treatment_forms": self.treatment_forms,
            "editorial_punctuation": self.editorial_punctuation,
            "title_treatment": self.title_treatment,
            "internal_conventions": self.internal_conventions,
            "register": self.register,
            "predominant_treatment": self.predominant_treatment,
            "punctuation_standard": self.punctuation_standard,
            "project_id": str(self.project_id),
            "tone": self.tone,
            "custom_rules": self.custom_rules,
            "metadata": self.metadata,
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StyleBible:
        """Reconstrói uma Style Bible a partir de um dicionário."""
        rules_dict: dict[str, StyleRule] = {}
        for k, v in data.get("rules", {}).items():
            if isinstance(v, dict):
                rules_dict[k] = StyleRule.from_dict(v)

        conventions = data.get("internal_conventions", [])
        if isinstance(conventions, str):
            conventions = [c.strip() for c in conventions.split(",") if c.strip()]

        sb = cls(
            narrator=data.get("narrator", "terceira pessoa"),
            narrative_person=data.get("narrative_person", "terceira pessoa"),
            predominant_tense=data.get("predominant_tense", "passado"),
            formality_level=data.get("formality_level", "formal"),
            dialogue_style=data.get("dialogue_style", "travessão"),
            profanity_handling=data.get("profanity_handling", "preservar intensidade do original"),
            treatment_forms=data.get("treatment_forms", "você"),
            editorial_punctuation=data.get("editorial_punctuation", "editorial brasileiro"),
            title_treatment=data.get("title_treatment", "traduzir"),
            internal_conventions=list(conventions),
            register=data.get("register", "literário contemporâneo"),
            predominant_treatment=data.get("predominant_treatment", "você"),
            punctuation_standard=data.get("punctuation_standard", "editorial brasileiro"),
            project_id=data.get("project_id", ""),
            tone=data.get("tone", "literário"),
            custom_rules=data.get("custom_rules", {}),
            metadata=data.get("metadata", {}),
            rules=rules_dict,
        )
        sb._sync_core_rules()
        return sb

    # =========================================================================
    # Validadores de Quality Assurance (QA) Programáticos
    # =========================================================================

    def validate_dialogue_style(self, target_text: str) -> list[StyleViolation]:
        """Valida se as marcações de diálogo respeitam a convenção definida.

        No padrão brasileiro editorial 'travessão', falas iniciadas com aspas inglesas
        são sinalizadas como violação. No padrão 'aspas', travessões são sinalizados.
        """
        violations: list[StyleViolation] = []
        lines = target_text.splitlines()

        is_em_dash_style = (
            "travessão" in self.dialogue_style.lower() or "travessao" in self.dialogue_style.lower()
        )
        is_quote_style = "aspas" in self.dialogue_style.lower()

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if is_em_dash_style:
                # Linha iniciando com aspas duplas inglesas como marcador de fala
                if line_str.startswith('"') and len(line_str) > 1 and not line_str.startswith('""'):
                    stripped_quote = line_str.strip('"')
                    violations.append(
                        StyleViolation(
                            rule_name="dialogue_style",
                            severity="warning",
                            message="Diálogo formatado com aspas quando a convenção da obra é travessão (—).",
                            snippet=line_str[:80],
                            suggested_fix=f"— {stripped_quote}",
                        )
                    )
            elif is_quote_style:
                # Linha iniciando com travessão quando o padrão é aspas
                if line_str.startswith(("—", "–", "- ")):
                    clean_text = re.sub(r"^[—–-]\s*", "", line_str)
                    violations.append(
                        StyleViolation(
                            rule_name="dialogue_style",
                            severity="warning",
                            message="Diálogo iniciado com travessão quando a convenção da obra é aspas.",
                            snippet=line_str[:80],
                            suggested_fix=f'"{clean_text}"',
                        )
                    )

        return violations

    def validate_punctuation(self, target_text: str) -> list[StyleViolation]:
        """Valida regras de pontuação editorial."""
        violations: list[StyleViolation] = []

        # 1. Dupla pontuação inconsistente (ex: .. ou ,,)
        for match in re.finditer(r"([,\.:;?!])\1+", target_text):
            seq = match.group(0)
            if seq not in ("...", "…", "??", "!!"):  # reticências e ênfases deliberadas permitidas
                violations.append(
                    StyleViolation(
                        rule_name="editorial_punctuation",
                        severity="warning",
                        message=f"Duplicação anômala de pontuação: '{seq}'.",
                        snippet=target_text[
                            max(0, match.start() - 15) : min(len(target_text), match.end() + 15)
                        ],
                        suggested_fix=seq[0],
                    )
                )

        # 2. Travessão sem espaço na abertura de fala (ex: '—Olá' em vez de '— Olá')
        for match in re.finditer(r"(^|\n)—[^\s\d—]", target_text):
            pos = match.start()
            violations.append(
                StyleViolation(
                    rule_name="editorial_punctuation",
                    severity="info",
                    message="Travessão de diálogo sem espaço após o travessão.",
                    snippet=target_text[pos : min(len(target_text), pos + 30)],
                    suggested_fix=match.group(0)[0] + "— " + match.group(0)[-1]
                    if match.group(0).startswith("\n")
                    else "— " + match.group(0)[-1],
                )
            )

        return violations

    def validate_profanity(
        self, source_text: str = "", target_text: str = ""
    ) -> list[StyleViolation]:
        """Valida se o tratamento de palavrões respeitou a diretriz editorial."""
        violations: list[StyleViolation] = []
        policy = (getattr(self, "profanity_policy", "") or self.profanity_handling).lower()
        target_lower = target_text.lower()

        if "censurar" in policy:
            explicit_bad_words = ["porra", "caralho", "foder", "merda", "puta"]
            for bad in explicit_bad_words:
                if re.search(rf"\b{bad}\b", target_lower):
                    violations.append(
                        StyleViolation(
                            rule_name="profanity",
                            severity="error",
                            message=f"Termo explícito '{bad}' encontrado. Diretriz da obra exige censura.",
                            snippet=target_text[:100],
                            suggested_fix=f"{bad[0]}***",
                        )
                    )
            return violations

        if not source_text:
            return violations

        # Detecta profanidades no texto fonte
        found_profanities: list[str] = []
        for word in ENGLISH_PROFANITIES:
            if re.search(rf"\b{word}\b", source_text, re.IGNORECASE):
                found_profanities.append(word)

        if not found_profanities:
            return violations

        if "preservar" in policy:
            # Deve haver termo correspondente com carga de intensidade
            for prof in found_profanities:
                expected_terms = ENGLISH_PROFANITIES[prof]
                has_match = any(t in target_lower for t in expected_terms)
                # Verifica se houve atenuação extrema ou omissão silenciosa
                if not has_match and not any(
                    w in target_lower for w in ["droga", "diabo", "raios", "inferno"]
                ):
                    violations.append(
                        StyleViolation(
                            rule_name="profanity",
                            severity="warning",
                            message=(
                                f"Termo de baixo calão '{prof}' no original aparenta ter sido omitido "
                                f"ou excessivamente atenuado. Diretriz: '{self.profanity_handling}'."
                            ),
                            snippet=source_text[:100],
                            suggested_fix=f"Considerar tradução com intensidade correspondente ({', '.join(expected_terms[:2])}).",
                        )
                    )

        return violations

    def validate_treatment(
        self, target_text: str, expected_treatment: str | None = None
    ) -> list[StyleViolation]:
        """Valida coerência no uso das formas de tratamento (você vs tu)."""
        violations: list[StyleViolation] = []
        treatment = (expected_treatment or self.treatment_forms).lower()

        # Busca formas pronominais e verbais de 2ª pessoa (tu/te/ti/contigo)
        tu_markers = re.findall(r"\b(tu|te|ti|contigo)\b", target_text, re.IGNORECASE)
        voce_markers = re.findall(r"\b(você|voce|vocês|voces)\b", target_text, re.IGNORECASE)

        if "você" in treatment or "voce" in treatment:
            if tu_markers:
                violations.append(
                    StyleViolation(
                        rule_name="treatment_forms",
                        severity="warning",
                        message=(
                            f"Uso de segunda pessoa 'tu' ({', '.join(set(tu_markers))}) no texto "
                            f"quando a diretriz da obra indica 'você'."
                        ),
                        snippet=target_text[:120],
                        suggested_fix="Uniformizar para 'você' conforme a diretriz da obra.",
                    )
                )
        elif "tu" in treatment:
            if voce_markers and not tu_markers:
                violations.append(
                    StyleViolation(
                        rule_name="treatment_forms",
                        severity="info",
                        message="Uso de 'você' quando a diretriz da obra indica predomínio de 'tu'.",
                        snippet=target_text[:120],
                        suggested_fix="Substituir por 'tu' se o contexto permitir.",
                    )
                )

        return violations

    def validate_title_treatment(self, source_text: str, target_text: str) -> list[StyleViolation]:
        """Valida conformidade na tradução de títulos de nobreza e cargos."""
        violations: list[StyleViolation] = []
        policy = self.title_treatment.lower()

        if "traduzir" in policy:
            for en_title, pt_title in NOBILITY_TITLES.items():
                if re.search(rf"\b{en_title}\b", source_text, re.IGNORECASE):
                    # Se manteve o termo em inglês no português sem tradução quando há tradução usual
                    if re.search(rf"\b{en_title}\b", target_text, re.IGNORECASE) and not re.search(
                        rf"\b{pt_title}\b", target_text, re.IGNORECASE
                    ):
                        if (
                            en_title.lower() != pt_title.lower()
                        ):  # ignora palavras idênticas como lady
                            violations.append(
                                StyleViolation(
                                    rule_name="title_treatment",
                                    severity="info",
                                    message=f"Título '{en_title}' mantido em inglês quando a diretriz é traduzir ('{pt_title}').",
                                    snippet=target_text[:100],
                                    suggested_fix=pt_title.capitalize(),
                                )
                            )
        elif any(w in policy for w in ["manter", "preservar", "original"]):
            for en_title, pt_title in NOBILITY_TITLES.items():
                if re.search(rf"\b{en_title}\b", source_text, re.IGNORECASE):
                    # Se traduziu para português quando a regra é manter original
                    if re.search(rf"\b{pt_title}\b", target_text, re.IGNORECASE) and not re.search(
                        rf"\b{en_title}\b", target_text, re.IGNORECASE
                    ):
                        if en_title.lower() != pt_title.lower():
                            violations.append(
                                StyleViolation(
                                    rule_name="title_treatment",
                                    severity="info",
                                    message=f"Título '{en_title}' traduzido para '{pt_title}' quando a diretriz é manter original.",
                                    snippet=target_text[:100],
                                    suggested_fix=en_title.capitalize(),
                                )
                            )

        return violations

    def validate_text(self, target_text: str, source_text: str = "") -> list[StyleViolation]:
        """Executa a suíte completa de verificações de estilo contra um texto traduzido."""
        violations: list[StyleViolation] = []
        violations.extend(self.validate_dialogue_style(target_text))
        violations.extend(self.validate_punctuation(target_text))
        violations.extend(self.validate_treatment(target_text))
        violations.extend(self.validate_profanity(source_text, target_text))
        if source_text:
            violations.extend(self.validate_title_treatment(source_text, target_text))
        return violations

    def get_explicit_rules(self) -> dict[str, StyleRule]:
        """Retorna apenas as regras de estilo comprovadas/explícitas."""
        return {k: r for k, r in self.rules.items() if not r.is_inferred}

    def get_inferred_rules(self) -> dict[str, StyleRule]:
        """Retorna apenas as regras de estilo deduzidas por inferência."""
        return {k: r for k, r in self.rules.items() if r.is_inferred}

    def detect_contradictions(self) -> list[Any]:
        """Detecta e sinaliza contradições internas nas diretrizes e evidências da Style Bible."""
        from book_translator.memory.models import ConflictReport

        conflicts: list[ConflictReport] = []

        # 1. Conflito entre Narrador e Pessoa Narrativa
        narrator_val = self.narrator.lower()
        person_val = self.narrative_person.lower()
        if ("primeira" in narrator_val or "1" in narrator_val) and (
            "terceira" in person_val or "3" in person_val
        ):
            conflicts.append(
                ConflictReport(
                    memory_type="style_bible",
                    term_or_name="narrator_vs_person",
                    existing_value=self.narrator,
                    conflicting_value=self.narrative_person,
                    reason=(
                        f"Inconsistência narrativa fundamental: narrador está definido como '{self.narrator}', "
                        f"mas a pessoa narrativa registrada é '{self.narrative_person}'."
                    ),
                    severity="error",
                    details={"narrator": self.narrator, "narrative_person": self.narrative_person},
                )
            )
        elif ("terceira" in narrator_val or "3" in narrator_val) and (
            "primeira" in person_val or "1" in person_val
        ):
            conflicts.append(
                ConflictReport(
                    memory_type="style_bible",
                    term_or_name="narrator_vs_person",
                    existing_value=self.narrator,
                    conflicting_value=self.narrative_person,
                    reason=(
                        f"Inconsistência narrativa fundamental: narrador está definido como '{self.narrator}', "
                        f"mas a pessoa narrativa registrada é '{self.narrative_person}'."
                    ),
                    severity="error",
                    details={"narrator": self.narrator, "narrative_person": self.narrative_person},
                )
            )

        # 2. Conflito entre Nível de Formalidade e Registro/Tom
        formality = (getattr(self, "formality", None) or self.formality_level).lower()
        tone_val = getattr(self, "tone", "").lower()
        if ("informal" in formality or "coloquial" in formality) and (
            "solene" in tone_val or "erudito" in tone_val
        ):
            conflicts.append(
                ConflictReport(
                    memory_type="style_bible",
                    term_or_name="formality_vs_tone",
                    existing_value=self.formality_level,
                    conflicting_value=self.tone,
                    reason=(
                        f"Contradição de registro: nível de formalidade '{self.formality_level}' "
                        f"conflita com o tom '{self.tone}'."
                    ),
                    severity="warning",
                    details={"formality_level": self.formality_level, "tone": self.tone},
                )
            )
        elif ("formal" in formality or "solene" in formality or "erudito" in formality) and (
            "coloquial" in tone_val
            or "informal" in tone_val
            or "gírias" in tone_val
            or "chulo" in tone_val
        ):
            conflicts.append(
                ConflictReport(
                    memory_type="style_bible",
                    term_or_name="formality_vs_tone",
                    existing_value=self.formality_level,
                    conflicting_value=self.tone,
                    reason=(
                        f"Contradição de registro: nível de formalidade '{self.formality_level}' "
                        f"conflita com o tom '{self.tone}'."
                    ),
                    severity="warning",
                    details={"formality_level": self.formality_level, "tone": self.tone},
                )
            )

        # 3. Conflito entre Padrão de Diálogo e Convenções Internas
        dial_style = self.dialogue_style.lower()
        conventions = self.internal_conventions
        if isinstance(conventions, str):
            conventions = [conventions]
        for conv in conventions:
            conv_lower = conv.lower()
            if "travessão" in dial_style and "aspas" in conv_lower and "diálogo" in conv_lower:
                conflicts.append(
                    ConflictReport(
                        memory_type="style_bible",
                        term_or_name="dialogue_convention_conflict",
                        existing_value=self.dialogue_style,
                        conflicting_value=conv,
                        reason=(
                            f"Convenção interna '{conv}' contradiz o padrão de diálogo "
                            f"estabelecido ('{self.dialogue_style}')."
                        ),
                        severity="error",
                        details={"dialogue_style": self.dialogue_style, "convention": conv},
                    )
                )

        # 4. Conflito entre Forma de Tratamento e Convenções Internas
        treatment = self.treatment_forms.lower()
        for conv in conventions:
            conv_lower = conv.lower()
            if "você" in treatment and "usar tu" in conv_lower:
                conflicts.append(
                    ConflictReport(
                        memory_type="style_bible",
                        term_or_name="treatment_convention_conflict",
                        existing_value=self.treatment_forms,
                        conflicting_value=conv,
                        reason=(
                            f"Convenção interna '{conv}' conflita com a forma de tratamento "
                            f"predominante ('{self.treatment_forms}')."
                        ),
                        severity="warning",
                        details={"treatment_forms": self.treatment_forms, "convention": conv},
                    )
                )

        # 5. Conflito entre regras registradas para a mesma dimensão
        rules_by_dim: dict[str, list[StyleRule]] = {}
        for rk, rule in self.rules.items():
            dim = getattr(rule, "dimension", "") or rule.name or rk
            if "treatment" in dim:
                dim = "treatment_forms"
            rules_by_dim.setdefault(dim, []).append(rule)

        for dim, r_list in rules_by_dim.items():
            if len(r_list) >= 2:
                distinct_vals = {r.value.strip().lower() for r in r_list if r.value.strip()}
                if len(distinct_vals) > 1:
                    conflicts.append(
                        ConflictReport(
                            memory_type="style_bible",
                            term_or_name=f"conflict_{dim}",
                            existing_value=r_list[0].value,
                            conflicting_value=r_list[1].value,
                            reason=f"Regras conflitantes registradas para '{dim}': '{r_list[0].value}' vs '{r_list[1].value}'.",
                            severity="error" if any(r.locked for r in r_list) else "warning",
                            details={"dimension": dim},
                        )
                    )

        # 5. Conflito entre Regra e Evidências Textuais
        for rname, rule in self.rules.items():
            if not rule.evidences:
                continue

            if rname in ("narrator", "narrative_person") and (
                "terceira" in rule.value.lower() or "3" in rule.value.lower()
            ):
                for ev in rule.evidences:
                    text_ev = ev.snippet.strip()
                    first_person_markers = re.findall(
                        r"\b(eu|meu|minha|meus|minhas|i|my|mine|we|our)\b", text_ev, re.IGNORECASE
                    )
                    if len(first_person_markers) >= 2 and not text_ev.startswith(('"', "—", "“")):
                        conflicts.append(
                            ConflictReport(
                                memory_type="style_bible",
                                term_or_name=f"evidence_conflict_{rname}",
                                existing_value=rule.value,
                                conflicting_value=text_ev[:60],
                                reason=(
                                    f"Evidência textual para '{rname}' contém marcadores explícitos "
                                    f"de 1ª pessoa ({', '.join(first_person_markers[:3])}), contradizendo "
                                    f"o valor registrado ('{rule.value}')."
                                ),
                                severity="warning",
                                details={
                                    "rule_name": rname,
                                    "snippet": text_ev,
                                    "chapter_id": ev.chapter_id,
                                },
                            )
                        )

            if rule.is_inferred and rule.locked:
                conflicts.append(
                    ConflictReport(
                        memory_type="style_bible",
                        term_or_name=f"inferred_locked_rule_{rname}",
                        existing_value="locked=True",
                        conflicting_value="is_inferred=True",
                        reason=(
                            f"Regra de estilo '{rname}' está marcada simultaneamente como inferência "
                            f"(is_inferred=True) e travada (locked=True). Regras travadas devem ser explícitas."
                        ),
                        severity="warning",
                        details={"rule_name": rname},
                    )
                )

        return conflicts
