"""Cent-exact validation of linked bank allocations before save or restore."""
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
ALLOWED = {"expense": {"Costo Fisso", "Costo Variabile", "Investimento"},
           "income": {"Stipendio", "Entrate aggiuntive", "Disinvestimento"}}


def cents(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Importo quota non valido")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number > Decimal("999999999.99") or number * 100 != (number * 100).to_integral_value():
            raise ValueError("Quote positive, con massimo due decimali")
        return int(number * 100)
    except InvalidOperation as error:
        raise ValueError("Importo quota non valido") from error


def validate_bank_allocations(state, records=()):
    sources = {record.get("id"): record for record in records if isinstance(record, dict) and record.get("id")}
    periods = [state]
    periods.extend(state.get("monthlyHistory", []))
    drafts = state.get("monthDrafts") or {}
    if not isinstance(drafts, dict):
        raise ValueError("Bozze mensili non valide")
    for key, draft in drafts.items():
        if isinstance(draft, dict):
            year, _, month = key.partition("-")
            periods.append({**draft, "year": year, "monthName": next((m for m in MONTHS if m.lower() == month), "")})
    for period in periods:
        if not isinstance(period, dict):
            continue
        groups = {}
        period_notes = period.get("notes") or []
        if not isinstance(period_notes, list):
            raise ValueError("Voci mensili non valide")
        for note in period_notes:
            if isinstance(note, dict) and note.get("bankTransactionId"):
                groups.setdefault(note["bankTransactionId"], []).append(note)
        ids = set()
        for identifier, notes in groups.items():
            # Legacy records remain loadable; every newly written allocation is
            # versioned. Include all siblings once any part uses this model.
            if not any(note.get("bankSplitVersion") for note in notes):
                continue
            if len(notes) > 50:
                raise ValueError("Al massimo 50 quote per movimento")
            source = sources.get(identifier)
            totals = {cents(note.get("bankOriginalAmount")) for note in notes if note.get("bankSplitVersion")}
            if len(totals) != 1:
                raise ValueError("Le quote non hanno lo stesso importo originale")
            total = next(iter(totals))
            if source and (source.get("currency") != "EUR" or cents(source.get("amount")) != total):
                raise ValueError("Importo originale diverso dal movimento bancario")
            assigned = 0
            for note in notes:
                child_id = note.get("id")
                if not isinstance(child_id, str) or not child_id or child_id in ids:
                    raise ValueError("Identificativo quota duplicato o mancante")
                if sum(1 for sibling in period_notes if isinstance(sibling, dict) and sibling.get("id") == child_id) != 1:
                    raise ValueError("Identificativo quota già utilizzato")
                ids.add(child_id)
                label = note.get("label")
                if not isinstance(label, str) or not label.strip() or len(label.strip()) > 120:
                    raise ValueError("Nome quota non valido")
                kind = source.get("recordType") if source else note.get("bankRecordType")
                if kind != note.get("bankRecordType") or note.get("category") not in ALLOWED.get(kind, set()):
                    raise ValueError("Categoria quota incompatibile con il movimento")
                try:
                    day = date.fromisoformat(note.get("transactionDate", ""))
                    month = MONTHS.index(period.get("monthName")) + 1
                    if day.year != int(period.get("year")) or day.month != month:
                        raise ValueError("Quota nel mese sbagliato")
                    if source and (source.get("date") != day.isoformat() or source.get("description") != note.get("originalBankDescription")):
                        raise ValueError("Riferimento originale del movimento alterato")
                except (TypeError, ValueError) as error:
                    raise ValueError("Data o riferimento quota non valido") from error
                assigned += cents(note.get("amount"))
            if assigned > total:
                raise ValueError("Le quote superano l’importo del movimento originale")
