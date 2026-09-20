"""Motor de Garantia de Qualidade Determinístico (Rule-Based QA sem IA)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from book_translator.core.models import Segment
from book_translator.logging import get_logger
from book_translator.qa.base import (
    IssueSeverity,
    QAFixAuditRecord,
    QAInterface,
    QAIssue,
    QAReport,
)

logger = get_logger("qa.deterministic")


class DeterministicQAEngine(QAInterface):
    """Validador de qualidade determinístico executando 13 verificações sem dependência de IA."""

    MONTHS_EN_PT: dict[str, str] = {
        "january": "janeiro",
        "february": "fevereiro",
        "march": "março",
        "april": "abril",
        "may": "maio",
        "june": "junho",
        "july": "julho",
        "august": "agosto",
        "september": "setembro",
        "october": "outubro",
        "november": "novembro",
        "december": "dezembro",
    }

    MEASUREMENTS_MAP: dict[str, str] = {
        "miles": "milhas",
        "mile": "milha",
        "feet": "pés",
        "foot": "pé",
        "inches": "polegadas",
        "inch": "polegada",
        "yards": "jardas",
        "yard": "jarda",
        "pounds": "libras",
        "pound": "libra",
        "ounces": "onças",
        "ounce": "onça",
    }

    CURRENCY_MAP: dict[str, str] = {
        "$": "dólar",
        "£": "libra",
        "€": "euro",
        "¥": "iene",
    }

    def evaluate(
        self,
        segment: Segment,
        original_text: str,
        translated_text: str,
        context: Any = None,
        glossary: list[Any] | None = None,
        characters: list[Any] | None = None,
    ) -> QAReport:
        """Executa as 13 verificações determinísticas no par source/target."""
        src = original_text.strip()
        tgt = translated_text.strip()
        issues: list[QAIssue] = []

        if not src:
            return QAReport(segment_id=segment.id, passed=True, issues=[])

        # Extrai glossário e personagens do contexto se fornecido
        active_glossary = glossary
        active_characters = characters
        if context is not None:
            if active_glossary is None and hasattr(context, "relevant_glossary"):
                active_glossary = getattr(context, "relevant_glossary", [])
            if active_characters is None and hasattr(context, "active_characters"):
                active_characters = getattr(context, "active_characters", [])

        # 1. Números
        issues.extend(self._check_numbers(src, tgt))

        # 2. Datas
        issues.extend(self._check_dates(src, tgt))

        # 3. Percentuais
        issues.extend(self._check_percentages(src, tgt))

        # 4. Moedas
        issues.extend(self._check_currencies(src, tgt))

        # 5. Medidas
        issues.extend(self._check_measurements(src, tgt))

        # 6. Nomes Próprios
        issues.extend(self._check_proper_names(src, tgt, active_characters))

        # 7. URLs e E-mails
        issues.extend(self._check_urls_and_emails(src, tgt))

        # 8. Notas de rodapé
        issues.extend(self._check_footnotes(src, tgt))

        # 9. Referências
        issues.extend(self._check_references(src, tgt))

        # 10. Termos Locked
        issues.extend(self._check_locked_terms(src, tgt, active_glossary))

        # 11. Presença/Ausência de Negações
        issues.extend(self._check_polarity(src, tgt))

        # 12. Contagem Estrutural
        issues.extend(self._check_structural_count(src, tgt))

        # 13. Conteúdo Omitido ou Duplicado
        issues.extend(self._check_omission_and_duplication(src, tgt))

        passed = len(issues) == 0
        return QAReport(segment_id=segment.id, passed=passed, issues=issues)

    # -------------------------------------------------------------------------
    # 1. Números
    # -------------------------------------------------------------------------
    def _check_numbers(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        # Captura sequências numéricas inteiras ou com pontuação
        src_raw = re.findall(r"\b\d+(?:[\.,]\d+)*\b", source)
        tgt_raw = re.findall(r"\b\d+(?:[\.,]\d+)*\b", target)

        def normalize_num(n: str) -> str:
            # Remove separadores de milhares para comparar dígitos essenciais
            return re.sub(r"[\.,]", "", n)

        src_nums = [normalize_num(n) for n in src_raw]
        tgt_nums = [normalize_num(n) for n in tgt_raw]

        for s_idx, s_n in enumerate(src_nums):
            if s_n not in tgt_nums:
                orig_snippet = src_raw[s_idx]
                trans_candidate = tgt_raw[s_idx] if s_idx < len(tgt_raw) else ""
                issues.append(
                    QAIssue(
                        check_type="number_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Número '{orig_snippet}' presente no original não foi encontrado na tradução.",
                        original_snippet=orig_snippet,
                        translated_snippet=trans_candidate,
                        suggested_fix=orig_snippet,
                    )
                )
        return issues

    # -------------------------------------------------------------------------
    # 2. Datas
    # -------------------------------------------------------------------------
    def _check_dates(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []

        # 1. Anos de 4 dígitos (ex: 1887, 1920, 2024)
        src_years = set(re.findall(r"\b(?:1[7-9][0-9]{2}|20[0-2][0-9])\b", source))
        tgt_years = set(re.findall(r"\b(?:1[7-9][0-9]{2}|20[0-2][0-9])\b", target))

        missing_years = src_years - tgt_years
        for yr in missing_years:
            trans_year = next(iter(tgt_years - src_years), "")
            issues.append(
                QAIssue(
                    check_type="date_mismatch",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=f"Ano '{yr}' do original ausente ou divergente na tradução.",
                    original_snippet=yr,
                    translated_snippet=trans_year,
                    suggested_fix=yr,
                )
            )

        # 2. Mês + Dia (ex: October 14, 14th of October)
        month_pattern = "|".join(self.MONTHS_EN_PT.keys())
        date_pattern = re.compile(
            rf"\b({month_pattern})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b|\b(\d{{1,2}})(?:st|nd|rd|th)?\s+of\s+({month_pattern})\b",
            re.IGNORECASE,
        )

        for match in date_pattern.finditer(source):
            full_match = match.group(0)
            if match.group(1):
                month_en = match.group(1).lower()
                day = match.group(2)
            else:
                day = match.group(3)
                month_en = match.group(4).lower()

            month_pt = self.MONTHS_EN_PT.get(month_en, "")
            expected_date = f"{day} de {month_pt}"

            # Procura dia e mês na tradução
            tgt_date_pattern = re.compile(rf"\b(\d{{1,2}})\s+de\s+({month_pt})\b", re.IGNORECASE)
            tgt_match = tgt_date_pattern.search(target)

            if not tgt_match:
                # Procura se há algum dia diferente com esse mês no target
                alt_day_match = re.search(r"\b(\d{1,2})\s+de\s+[a-zç]+\b", target, re.IGNORECASE)
                trans_snippet = alt_day_match.group(0) if alt_day_match else ""
                issues.append(
                    QAIssue(
                        check_type="date_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Data '{full_match}' alterada ou ausente. Esperado: '{expected_date}'.",
                        original_snippet=full_match,
                        translated_snippet=trans_snippet,
                        suggested_fix=expected_date,
                    )
                )
            elif tgt_match.group(1) != day:
                issues.append(
                    QAIssue(
                        check_type="date_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Dia da data alterado: esperado '{day}', encontrado '{tgt_match.group(1)}'.",
                        original_snippet=full_match,
                        translated_snippet=tgt_match.group(0),
                        suggested_fix=expected_date,
                    )
                )

        # 3. Mês isolado ou associado a ano (ex: "August 1914" vs "setembro de 1914")
        for m_en, m_pt in self.MONTHS_EN_PT.items():
            m_match = re.search(rf"\b({m_en})\b", source, re.IGNORECASE)
            if m_match:
                orig_m = m_match.group(0)
                if not re.search(rf"\b{m_pt}\b", target, re.IGNORECASE):
                    all_pt_months = "|".join(self.MONTHS_EN_PT.values())
                    other_pt = re.search(rf"\b({all_pt_months})\b", target, re.IGNORECASE)
                    trans_m = other_pt.group(0) if other_pt else ""
                    already_reported = any(m_en.lower() in i.original_snippet.lower() for i in issues)
                    if not already_reported:
                        issues.append(
                            QAIssue(
                                check_type="date_mismatch",
                                severity=IssueSeverity.REVIEW_REQUIRED,
                                description=f"Mês '{orig_m}' alterado ou ausente na tradução (esperado '{m_pt}').",
                                original_snippet=orig_m,
                                translated_snippet=trans_m,
                                suggested_fix=m_pt,
                            )
                        )

        return issues

    # -------------------------------------------------------------------------
    # 3. Percentuais
    # -------------------------------------------------------------------------
    def _check_percentages(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        src_pcts = re.findall(r"\b(\d+(?:[\.,]\d+)?)\s*(?:%|percent\b)", source, re.IGNORECASE)
        tgt_pcts = re.findall(r"\b(\d+(?:[\.,]\d+)?)\s*(?:%|por\s*cento\b)", target, re.IGNORECASE)

        for p in src_pcts:
            clean_p = p.replace(".", ",")
            if p not in tgt_pcts and clean_p not in tgt_pcts:
                issues.append(
                    QAIssue(
                        check_type="percentage_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Percentual '{p}%' divergente ou ausente na tradução.",
                        original_snippet=f"{p}%",
                        translated_snippet=next(iter(tgt_pcts), ""),
                        suggested_fix=f"{clean_p}%",
                    )
                )

        # Checa espaçamento indevido antes do símbolo de % no target (ex: "15 %" -> "15%")
        for m in re.finditer(r"\b(\d+)\s+%", target):
            issues.append(
                QAIssue(
                    check_type="percentage_mismatch",
                    severity=IssueSeverity.SAFE_FIX,
                    description=f"Espaço espúrio antes do símbolo percentual '{m.group(0)}'.",
                    original_snippet="%",
                    translated_snippet=m.group(0),
                    suggested_fix=f"{m.group(1)}%",
                )
            )

        return issues

    # -------------------------------------------------------------------------
    # 4. Moedas
    # -------------------------------------------------------------------------
    def _check_currencies(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []

        # Detecta símbolos monetários e valores ($50, £100, €20)
        for sym in ["$", "£", "€", "¥"]:
            src_amounts = re.findall(rf"\{sym}\s*(\d+(?:[\.,]\d+)?)", source)
            for amt in src_amounts:
                # No target, pode aparecer como £50, 50 libras, $50, etc.
                if sym == "£":
                    valid = (
                        f"£{amt}" in target
                        or f"£ {amt}" in target
                        or f"{amt} libras" in target.lower()
                    )
                elif sym == "$":
                    valid = (
                        f"${amt}" in target
                        or f"$ {amt}" in target
                        or f"{amt} dólares" in target.lower()
                    )
                elif sym == "€":
                    valid = (
                        f"€{amt}" in target
                        or f"€ {amt}" in target
                        or f"{amt} euros" in target.lower()
                    )
                else:
                    valid = sym in target

                if not valid:
                    issues.append(
                        QAIssue(
                            check_type="currency_mismatch",
                            severity=IssueSeverity.REVIEW_REQUIRED,
                            description=f"Valor monetário '{sym}{amt}' não preservado na tradução.",
                            original_snippet=f"{sym}{amt}",
                            translated_snippet="",
                            suggested_fix=f"{sym}{amt}",
                        )
                    )
        return issues

    # -------------------------------------------------------------------------
    # 5. Medidas
    # -------------------------------------------------------------------------
    def _check_measurements(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        for unit_en, unit_pt in self.MEASUREMENTS_MAP.items():
            pattern = re.compile(rf"\b(\d+(?:[\.,]\d+)?)\s+{unit_en}\b", re.IGNORECASE)
            for m in pattern.finditer(source):
                val = m.group(1)
                expected = f"{val} {unit_pt}"

                # Se a unidade em inglês ainda permaneceu no target
                if re.search(rf"\b{val}\s+{unit_en}\b", target, re.IGNORECASE):
                    issues.append(
                        QAIssue(
                            check_type="measurement_mismatch",
                            severity=IssueSeverity.SAFE_FIX,
                            description=f"Unidade de medida não traduzida: '{val} {unit_en}'.",
                            original_snippet=m.group(0),
                            translated_snippet=f"{val} {unit_en}",
                            suggested_fix=expected,
                        )
                    )
                # Se o valor nem a unidade traduzida foram encontrados
                elif not re.search(rf"\b{val}\s+{unit_pt}\b", target, re.IGNORECASE):
                    issues.append(
                        QAIssue(
                            check_type="measurement_mismatch",
                            severity=IssueSeverity.SUGGESTED_FIX,
                            description=f"Medida '{m.group(0)}' divergente na tradução.",
                            original_snippet=m.group(0),
                            translated_snippet="",
                            suggested_fix=expected,
                        )
                    )
        return issues

    # -------------------------------------------------------------------------
    # 6. Nomes Próprios
    # -------------------------------------------------------------------------
    def _check_proper_names(
        self, source: str, target: str, characters: list[Any] | None
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        if not characters:
            return issues

        for char in characters:
            canonical = getattr(char, "canonical_name", "")
            if not canonical or len(canonical) < 3:
                continue

            # Se o nome canônico completo estava no original
            if canonical.lower() in source.lower():
                # Verifica se está no target
                if canonical.lower() not in target.lower():
                    # Verifica se há typo ou menção parcial (ex: "Sherlock Holms" em vez de "Sherlock Holmes")
                    parts = canonical.split()
                    last_name = parts[-1] if len(parts) > 1 else canonical

                    # Procura por proximidade
                    typo_pattern = re.compile(rf"\b{parts[0]}\s+([a-zA-Z]{{3,}})\b", re.IGNORECASE)
                    match = typo_pattern.search(target)

                    if match and match.group(0).lower() != canonical.lower():
                        issues.append(
                            QAIssue(
                                check_type="proper_name_inconsistency",
                                severity=IssueSeverity.SUGGESTED_FIX,
                                description=f"Inconsistência no nome próprio '{canonical}': encontrado '{match.group(0)}'.",
                                original_snippet=canonical,
                                translated_snippet=match.group(0),
                                suggested_fix=canonical,
                            )
                        )
                    elif last_name.lower() not in target.lower():
                        issues.append(
                            QAIssue(
                                check_type="proper_name_inconsistency",
                                severity=IssueSeverity.REVIEW_REQUIRED,
                                description=f"Nome canônico do personagem '{canonical}' omitido na tradução.",
                                original_snippet=canonical,
                                translated_snippet="",
                                suggested_fix=canonical,
                            )
                        )
        return issues

    # -------------------------------------------------------------------------
    # 7. URLs e E-mails
    # -------------------------------------------------------------------------
    def _check_urls_and_emails(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        url_pattern = re.compile(r"https?://[^\s)\]]+|www\.[^\s)\]]+", re.IGNORECASE)
        email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

        for url in url_pattern.findall(source):
            if url not in target:
                # Encontra URL corrompida no target
                tgt_urls = url_pattern.findall(target)
                corrupt = tgt_urls[0] if tgt_urls else ""
                issues.append(
                    QAIssue(
                        check_type="url_mismatch",
                        severity=IssueSeverity.SAFE_FIX,
                        description=f"URL '{url}' corrompida ou ausente na tradução.",
                        original_snippet=url,
                        translated_snippet=corrupt,
                        suggested_fix=url,
                    )
                )

        for email in email_pattern.findall(source):
            if email.lower() not in target.lower():
                issues.append(
                    QAIssue(
                        check_type="url_mismatch",
                        severity=IssueSeverity.SAFE_FIX,
                        description=f"E-mail '{email}' não preservado na tradução.",
                        original_snippet=email,
                        translated_snippet="",
                        suggested_fix=email,
                    )
                )
        return issues

    # -------------------------------------------------------------------------
    # 8. Notas de Rodapé
    # -------------------------------------------------------------------------
    def _check_footnotes(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        fn_pattern = re.compile(r"\[\^?\d+\]")
        src_fns = fn_pattern.findall(source)
        tgt_fns = fn_pattern.findall(target)

        for fn in src_fns:
            if fn not in tgt_fns:
                issues.append(
                    QAIssue(
                        check_type="footnote_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Marcador de nota de rodapé '{fn}' ausente na tradução.",
                        original_snippet=fn,
                        translated_snippet="",
                        suggested_fix=fn,
                    )
                )
        return issues

    # -------------------------------------------------------------------------
    # 9. Referências
    # -------------------------------------------------------------------------
    def _check_references(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        # Citações como (Smith, 2020) ou [Capítulo 3]
        cite_pattern = re.compile(r"\([A-Z][a-z]+,\s*\d{4}\)")
        for cite in cite_pattern.findall(source):
            if cite not in target:
                issues.append(
                    QAIssue(
                        check_type="reference_mismatch",
                        severity=IssueSeverity.REVIEW_REQUIRED,
                        description=f"Citação bibliográfica '{cite}' não preservada na tradução.",
                        original_snippet=cite,
                        translated_snippet="",
                        suggested_fix=cite,
                    )
                )
        return issues

    # -------------------------------------------------------------------------
    # 10. Termos Locked
    # -------------------------------------------------------------------------
    def _check_locked_terms(
        self, source: str, target: str, glossary: list[Any] | None
    ) -> list[QAIssue]:
        issues: list[QAIssue] = []
        if not glossary:
            return issues

        for entry in glossary:
            if not getattr(entry, "locked", False):
                continue

            src_term = getattr(entry, "source_term", "").strip()
            tgt_term = getattr(entry, "target_term", "").strip()

            if not src_term or not tgt_term:
                continue

            # Se o termo em inglês está no source
            src_pat = re.compile(rf"\b{re.escape(src_term)}\b", re.IGNORECASE)
            if src_pat.search(source):
                # Se o termo em inglês permaneceu indevidamente no target -> SAFE FIX
                tgt_src_match = src_pat.search(target)
                if tgt_src_match and src_term.lower() != tgt_term.lower():
                    issues.append(
                        QAIssue(
                            check_type="locked_term_violation",
                            severity=IssueSeverity.SAFE_FIX,
                            description=f"Termo travado '{src_term}' permaneceu sem tradução. Deve ser '{tgt_term}'.",
                            original_snippet=src_term,
                            translated_snippet=tgt_src_match.group(0),
                            suggested_fix=tgt_term,
                        )
                    )
                else:
                    # Se o termo traduzido não está presente no target
                    tgt_pat = re.compile(rf"\b{re.escape(tgt_term)}\b", re.IGNORECASE)
                    if not tgt_pat.search(target):
                        issues.append(
                            QAIssue(
                                check_type="locked_term_violation",
                                severity=IssueSeverity.REVIEW_REQUIRED,
                                description=f"Termo obrigatório travado '{tgt_term}' ausente na tradução.",
                                original_snippet=src_term,
                                translated_snippet="",
                                suggested_fix=tgt_term,
                            )
                        )
        return issues

    # -------------------------------------------------------------------------
    # 11. Presença/Ausência de Negações (Polaridade)
    # -------------------------------------------------------------------------
    def _check_polarity(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        en_neg_pattern = re.compile(
            r"\b(not|never|neither|nor|no\s+\w+|nobody|nothing|nowhere|cannot|can't|didn't|doesn't|wasn't|weren't|won't|wouldn't|shouldn't|haven't|hasn't)\b",
            re.IGNORECASE,
        )
        pt_neg_pattern = re.compile(
            r"\b(não|nunca|jamais|nenhum|nenhuma|ninguém|nada|nem|tampouco)\b",
            re.IGNORECASE,
        )

        has_en_neg = bool(en_neg_pattern.search(source))
        has_pt_neg = bool(pt_neg_pattern.search(target))

        if has_en_neg and not has_pt_neg:
            neg_word = en_neg_pattern.search(source).group(0)  # type: ignore
            issues.append(
                QAIssue(
                    check_type="polarity_mismatch",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description="Inversão de polaridade: oração negativa no original traduzida sem negação.",
                    original_snippet=neg_word,
                    translated_snippet=target[:50],
                    suggested_fix=None,
                )
            )
        elif not has_en_neg and has_pt_neg:
            # Source é puramente afirmativo, mas target tem negação
            neg_word = pt_neg_pattern.search(target).group(0)  # type: ignore
            issues.append(
                QAIssue(
                    check_type="polarity_mismatch",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description="Inversão de polaridade: oração afirmativa no original traduzida com negação espúria.",
                    original_snippet=source[:50],
                    translated_snippet=neg_word,
                    suggested_fix=None,
                )
            )

        return issues

    # -------------------------------------------------------------------------
    # 12. Contagem Estrutural
    # -------------------------------------------------------------------------
    def _check_structural_count(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []
        src_sentences = [s.strip() for s in re.split(r"[.!?]+", source) if s.strip()]
        tgt_sentences = [s.strip() for s in re.split(r"[.!?]+", target) if s.strip()]

        if len(src_sentences) >= 3 and len(tgt_sentences) == 1 and len(target) < 0.6 * len(source):
            issues.append(
                QAIssue(
                    check_type="structural_count_mismatch",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description=f"Divergência estrutural: {len(src_sentences)} orações no original colapsadas em {len(tgt_sentences)} na tradução.",
                    original_snippet=f"{len(src_sentences)} orações",
                    translated_snippet=f"{len(tgt_sentences)} orações",
                )
            )
        return issues

    # -------------------------------------------------------------------------
    # 13. Omissão ou Duplicação por Erro de Pipeline
    # -------------------------------------------------------------------------
    def _check_omission_and_duplication(self, source: str, target: str) -> list[QAIssue]:
        issues: list[QAIssue] = []

        # Omissão severa (< 35% do comprimento de caracteres quando source > 40 caracteres)
        if len(source) > 40 and len(target) < 0.35 * len(source):
            issues.append(
                QAIssue(
                    check_type="omission_or_duplication",
                    severity=IssueSeverity.REVIEW_REQUIRED,
                    description="Truncamento severo: comprimento da tradução é inferior a 35% do texto original.",
                    original_snippet=source,
                    translated_snippet=target,
                )
            )

        # Duplicação contígua de sentença ou frase longa
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", target) if len(s.strip()) >= 15]
        for i in range(len(sentences) - 1):
            if sentences[i] == sentences[i + 1]:
                dup_text = sentences[i]
                issues.append(
                    QAIssue(
                        check_type="omission_or_duplication",
                        severity=IssueSeverity.SAFE_FIX,
                        description=f"Duplicação contígua de frase detectada na tradução: '{dup_text}'.",
                        original_snippet="",
                        translated_snippet=f"{dup_text} {dup_text}",
                        suggested_fix=dup_text,
                    )
                )

        return issues

    # -------------------------------------------------------------------------
    # Aplicação Auditável de SAFE FIX
    # -------------------------------------------------------------------------
    def apply_safe_fixes(
        self,
        segment_id: str,
        original_text: str,
        translated_text: str,
        report: QAReport,
    ) -> tuple[str, list[QAFixAuditRecord]]:
        """Aplica apenas as correções categorizadas como SAFE FIX gerando trilha de auditoria completa."""
        current_text = translated_text
        audit_records: list[QAFixAuditRecord] = []

        for issue in report.issues:
            if issue.severity != IssueSeverity.SAFE_FIX or not issue.suggested_fix:
                continue

            old_state = current_text

            # 1. Duplicação de frase contígua
            if issue.check_type == "omission_or_duplication" and issue.translated_snippet:
                dup_phrase = issue.suggested_fix
                # Substitui a repetição contígua da frase
                pattern = rf"\b{re.escape(dup_phrase)}\s+{re.escape(dup_phrase)}\b"
                if re.search(pattern, current_text):
                    current_text = re.sub(pattern, dup_phrase, current_text)

            # 2. Termo locked mantido em inglês
            elif issue.check_type == "locked_term_violation" and issue.original_snippet:
                src_term = issue.original_snippet
                tgt_term = issue.suggested_fix
                pattern = rf"\b{re.escape(src_term)}\b"
                current_text = re.sub(pattern, tgt_term, current_text, flags=re.IGNORECASE)

            # 3. URL restaurada
            elif issue.check_type == "url_mismatch" and issue.suggested_fix:
                correct_url = issue.suggested_fix
                corrupt_url = issue.translated_snippet
                if corrupt_url and corrupt_url in current_text:
                    current_text = current_text.replace(corrupt_url, correct_url)

            # 4. Espaço antes de percentual ("15 %" -> "15%")
            elif issue.check_type == "percentage_mismatch" and issue.translated_snippet:
                current_text = current_text.replace(issue.translated_snippet, issue.suggested_fix)

            # 5. Medidas em inglês traduzidas ("10 miles" -> "10 milhas")
            elif issue.check_type == "measurement_mismatch" and issue.translated_snippet:
                current_text = current_text.replace(issue.translated_snippet, issue.suggested_fix)

            if current_text != old_state:
                audit = QAFixAuditRecord(
                    id=f"fix_{segment_id}_{uuid.uuid4().hex[:8]}",
                    segment_id=segment_id,
                    check_type=issue.check_type,
                    old_text=old_state,
                    new_text=current_text,
                    rule_applied=f"safe_fix:{issue.check_type}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={
                        "original_snippet": issue.original_snippet,
                        "suggested_fix": issue.suggested_fix,
                    },
                )
                audit_records.append(audit)

        return current_text, audit_records
