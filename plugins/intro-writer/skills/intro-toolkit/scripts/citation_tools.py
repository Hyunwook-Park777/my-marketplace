#!/usr/bin/env python3
"""
Citation Tools - Introduction 인용·참고문헌 결정적 처리

하위 명령:
  crossref    paper_index.json 의 빈 서지 필드(DOI, 권, 쪽, 저널 약어)를 Crossref 로 채움.
              제목 유사도 ≥ 0.90 일 때만 채택. PDF 에서 읽은 값은 덮어쓰지 않고 불일치만 기록.
  references  intro_sources.json 의 인용 번호 ↔ 파일 매핑 + paper_index.json 서지로
              References.md 생성 (vancouver | authoryear). --embed 로 Introduction.md 의
              "## References" 절을 교체/추가.
  check       Introduction.md 본문 인용 [N], [N,M], [N-M] 을 intro_sources.json 과 대조:
              참고문헌 없는 번호, 인용되지 않은 참고문헌, 첫 등장 순서, 인용 문장 비율.
              오류가 있으면 종료 코드 1.

Usage:
    python citation_tools.py crossref   --index paper_index.json
    python citation_tools.py references --sources intro_sources.json --index paper_index.json \
        --output References.md [--style vancouver] [--embed Introduction.md]
    python citation_tools.py check      --intro Introduction.md --sources intro_sources.json \
        [--index paper_index.json] [--no-numbered] [--output citation_structure.json]
"""

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CITE_RE = re.compile(r"(?<![\w!\]])\[(\d+(?:\s*[-–—,]\s*\d+)*)\](?!\()")
REF_HEADING_RE = re.compile(r"^#{1,6}\s*References?\s*$", re.IGNORECASE | re.MULTILINE)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


DOI_PREFIX_RE = re.compile(r"^\s*(https?://(dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)


def norm_doi(doi: str) -> str:
    return DOI_PREFIX_RE.sub("", doi or "").strip().rstrip(".").lower()


def read_text(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, text: str):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def save_json(path: Path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


# ---------------------------------------------------------------- crossref
def _norm_title(t: str) -> str:
    # 유니코드 \w — 한글·악센트 문자를 지우면 서로 다른 한글 제목이 둘 다 "" 가 되어 유사도 1.0 이 된다
    t = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", t or "")).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", t)).strip()


def _get(url: str, timeout: int = 20, retries: int = 2):
    time.sleep(0.2)  # Crossref 공용 풀 예절
    req = urllib.request.Request(url, headers={"User-Agent": "intro-writer/2.5 (citation_tools.py)"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)["message"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries:
                raise
        except OSError:  # URLError, 타임아웃, 연결 리셋
            if attempt == retries:
                raise
        time.sleep(2 * (attempt + 1))


def _similarity(a: str, b: str) -> float:
    na, nb = _norm_title(a), _norm_title(b)
    if len(na) < 10 or len(nb) < 10:  # 빈 제목·너무 짧은 제목은 비교 불가
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _item_titles(it: dict) -> list[str]:
    """Crossref 는 부제를 subtitle 에 따로 둔다 — 본제목과 '본제목: 부제' 둘 다 후보로."""
    title = (it.get("title") or [""])[0]
    subs = it.get("subtitle") or []
    return [title] + [f"{title}: {sub}" for sub in subs[:1]]


def _best_similarity(title: str, it: dict) -> float:
    return max(_similarity(title, t) for t in _item_titles(it))


def crossref_lookup(title: str):
    msg = _get("https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": title, "rows": 3}))
    best, score = None, 0.0
    for it in (msg or {}).get("items", []):
        s = _best_similarity(title, it)
        if s > score:
            best, score = it, s
    return best, score


def doi_record(doi: str):
    """DOI 의 Crossref 레코드. Crossref 에 없으면 None."""
    return _get("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/"))


def doi_exists_elsewhere(doi: str) -> bool:
    """DataCite·JaLC·KISTI 등 Crossref 밖 DOI 인지 doi.org 핸들 API 로 확인."""
    try:
        time.sleep(0.2)
        req = urllib.request.Request("https://doi.org/api/handles/" + urllib.parse.quote(doi, safe="/"),
                                     headers={"User-Agent": "intro-writer/2.5"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("responseCode") == 1
    except Exception:
        return False


def cmd_crossref(args):
    """빈 서지 필드를 채우고, 이미 있는 DOI 는 실제로 그 논문을 가리키는지 확인한다.

    LLM 이 요약 중 적은 DOI 는 형식만 그럴듯하고 다른 논문을 가리키는 경우가 있다
    (v2.4 산출물 12편 중 4편). 그래서 PDF 값이라도 DOI 는 제목 대조를 통과해야 남긴다.
    """
    index = load_json(args.index)
    filled = fixed = 0
    for p in index["papers"]:
        # 재실행 시 이전 crossref 기록을 지우고 새로 판단한다
        p["bib_notes"] = [n for n in p.get("bib_notes", []) if not n.startswith(("crossref", "doi "))]
        p["verified_fields"] = []
        notes = p["bib_notes"]
        if p.get("doi"):
            p["doi"] = norm_doi(p["doi"])
        if not p.get("title"):
            notes.append("crossref: no title, skipped")
            continue
        try:
            if p.get("doi"):
                rec = doi_record(p["doi"])
                if rec is None:
                    if doi_exists_elsewhere(p["doi"]):
                        notes.append(f"doi '{p['doi']}' exists outside Crossref; title unverified")
                    else:
                        notes.append(f"doi '{p['doi']}' rejected: does not resolve")
                        p["doi"] = ""
                        fixed += 1
                elif _best_similarity(p["title"], rec) < args.min_similarity:
                    t = (rec.get("title") or [""])[0]
                    notes.append(f"doi '{p['doi']}' rejected: resolves to '{t[:80]}'")
                    p["doi"] = ""
                    fixed += 1
                else:
                    p["verified_fields"].append("doi")
            item, score = crossref_lookup(p["title"])
        except Exception as e:  # 네트워크 실패는 치명적이지 않다 — 빈 칸으로 남긴다
            notes.append(f"crossref: lookup failed ({type(e).__name__})")
            continue
        p["crossref_similarity"] = round(score, 3)
        if not item or score < args.min_similarity:
            notes.append(f"crossref: no confident match (similarity {score:.2f})")
            continue
        found = {
            "doi": norm_doi(item.get("DOI", "")),
            "journal": (item.get("container-title") or [""])[0],
            "journal_abbrev": (item.get("short-container-title") or [""])[0],
            "issue": item.get("issue", ""),
            "pages": item.get("page", "") or item.get("article-number", ""),
            "year": str((item.get("issued", {}).get("date-parts") or [[""]])[0][0] or ""),
        }
        if p.get("doc_type", "journal") == "journal":  # SAE·학회 논문의 Crossref volume 은 의미 없음
            found["volume"] = item.get("volume", "")
        cr_authors = [{"family": a.get("family", ""), "given": a.get("given", "")}
                      for a in item.get("author") or [] if a.get("family")]
        if cr_authors:
            mine = _author_dicts(p.get("authors"))
            # 원문 저자란이 깨졌다고 표시됐거나 비어 있으면 Crossref 저자로 교체 (제목 일치가 확인된 레코드)
            if not mine or p.get("author_quality") == "garbled":
                p["authors"] = cr_authors
                p["author_quality"] = "crossref"
                p["verified_fields"].append("authors")
            elif [a["family"].lower() for a in mine] != [a["family"].lower() for a in cr_authors]:
                notes.append("crossref conflict on authors: pdf=" + ", ".join(a["family"] for a in mine)
                             + " crossref=" + ", ".join(a["family"] for a in cr_authors) + " (pdf kept)")
        for k, v in found.items():
            if not v:
                continue
            mine = str(p.get(k, "") or "")
            if not mine:
                p[k] = v
                p.setdefault("verified_fields", []).append(k)
                filled += 1
            elif k in ("doi", "year", "volume") and mine.lower() != v.lower():
                notes.append(f"crossref conflict on {k}: pdf='{mine}' crossref='{v}' (pdf kept)")
        p["verified_fields"] = list(dict.fromkeys(p["verified_fields"]))
        if not notes:
            del p["bib_notes"]
    save_json(args.index, index)
    conflicts = sum(1 for p in index["papers"] for n in p.get("bib_notes", []) if "conflict" in n)
    print(f"crossref: filled {filled} fields, rejected {fixed} wrong DOIs, "
          f"{conflicts} conflicts, {len(index['papers'])} papers")
    for p in index["papers"]:
        for n in p.get("bib_notes", []):
            print(f"  {p['file']}: {n}")


# ---------------------------------------------------------------- references
ETAL_RE = re.compile(r"^(et\s*)?al\.?$", re.IGNORECASE)


def _initials(given: str) -> str:
    parts = re.split(r"[\s.\-]+", given or "")
    return "".join(p[0].upper() for p in parts if p)


def _author_dicts(authors) -> list[dict]:
    """문자열("Dr. Vipin Dhyani")·dict 혼용 저자 목록을 {family, given} 으로 통일, "et al." 제거."""
    out = []
    for a in authors or []:
        if isinstance(a, str):
            toks = re.sub(r"^(Dr|Prof)\.?(-Ing\.?)?\s+", "", a.strip()).split()
            a = {"family": toks[-1], "given": " ".join(toks[:-1])} if toks else {}
        fam = (a.get("family") or "").strip()
        full = f"{a.get('given') or ''} {fam}".strip()
        if fam and not ETAL_RE.match(fam) and not ETAL_RE.match(full):
            out.append({"family": fam, "given": (a.get("given") or "").strip()})
    return out


def _authors_vancouver(authors) -> str:
    names = [f"{a['family']} {_initials(a['given'])}".strip() for a in _author_dicts(authors)]
    if len(names) > 6:
        names = names[:6] + ["et al"]
    return ", ".join(names)


def _authors_apa(authors) -> str:
    def one(a):
        ini = " ".join(f"{c}." for c in _initials(a["given"]))
        return f"{a['family']}, {ini}" if ini else a["family"]
    names = [one(a) for a in _author_dicts(authors)]
    if len(names) <= 1:
        return "".join(names)
    if len(names) > 20:
        names = names[:19] + ["... " + names[-1]]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def _tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    s = re.sub(r"([?!])\.", r"\1", s)
    s = re.sub(r"\.{2,}", ".", s)
    return s.strip()


def format_reference(p: dict, style: str) -> str:
    journal = p.get("journal_abbrev") or p.get("journal") or ""
    title = (p.get("title") or "").strip().rstrip(".")
    year, vol, iss, pages = (str(p.get(k, "") or "") for k in ("year", "volume", "issue", "pages"))
    doi = norm_doi(p.get("doi", ""))
    # SAE Technical Paper·학회 논문의 Crossref volume 은 의미 없다 (SAE Transactions 만 권호 유지)
    if p.get("doc_type") in ("sae", "conference") and not journal.lower().startswith("sae trans"):
        vol = iss = ""
    if style == "authoryear":
        parts = [_authors_apa(p.get("authors")), f"({year or 'n.d.'}).", f"{title}."]
        src = journal
        if vol:
            src += f", {vol}" + (f"({iss})" if iss else "")
        if pages:
            src += f", {pages}"
        if src:
            parts.append(f"{src}.")
    else:
        authors = _authors_vancouver(p.get("authors"))
        parts = [f"{authors}." if authors else "", f"{title}."]
        src = " ".join(x for x in (journal, year) if x)
        if vol:
            src += f";{vol}" + (f"({iss})" if iss else "")
        if pages:
            src += f":{pages}"
        if src:
            parts.append(f"{src}.")
    if doi:
        parts.append(f"https://doi.org/{doi}")
    return _tidy(" ".join(x for x in parts if x))


def missing_fields(p: dict) -> list[str]:
    need = ["authors", "title", "journal", "year"]
    doc_type = p.get("doc_type", "journal")
    if doc_type == "journal":
        need += ["volume", "pages", "doi"]
    elif doc_type in ("sae", "conference"):
        need += ["pages"] if not p.get("doi") else []  # 쪽(또는 논문 번호)이나 DOI 중 하나는 있어야 찾을 수 있다
    miss = [k for k in need if not p.get(k)]
    if p.get("doc_type") in ("sae", "conference") and not p.get("doi") and not p.get("pages"):
        miss.append("doi or paper number")
    # 성이 빠진 저자는 References 에서 조용히 빠지므로 따로 알린다
    if any(isinstance(a, dict) and not (a.get("family") or "").strip() for a in p.get("authors") or []):
        miss.append("author without family name")
    if p.get("author_quality") == "garbled":
        miss.append("authors garbled in source (check byline)")
    return list(dict.fromkeys(miss))


def cmd_references(args):
    sources = load_json(args.sources)
    index = {p["file"]: p for p in load_json(args.index)["papers"]}
    refs = sorted(sources.get("references", []), key=lambda r: r["citation_number"])
    lines, incomplete, unknown = [], [], []
    for r in refs:
        p = index.get(r["source_file"])
        if not p:
            unknown.append(f"[{r['citation_number']}] {r['source_file']}")
            continue
        body = format_reference(p, args.style)
        lines.append(f"[{r['citation_number']}] {body}" if args.style == "vancouver" else body)
        if miss := missing_fields(p):
            incomplete.append(f"[{r['citation_number']}] {r['source_file']}: missing {', '.join(miss)}")
    if unknown:  # 서지를 지어내지 않는다 — paper_index 에 항목을 보완한 뒤 다시 실행
        print("ERROR: source_file not in paper_index.json (add an entry, then rerun):", file=sys.stderr)
        for u in unknown:
            print(f"  {u}", file=sys.stderr)
        sys.exit(1)
    if args.style == "authoryear":
        lines.sort(key=str.lower)
    block = "## References\n\n" + "\n\n".join(lines) + "\n"
    write_text(args.output, block)
    if args.embed:
        text = read_text(args.embed)
        m = REF_HEADING_RE.search(text)
        write_text(args.embed, (text[:m.start()].rstrip() if m else text.rstrip()) + "\n\n" + block)
    print(f"references: {len(lines)} entries -> {args.output}")
    for x in incomplete:
        print(f"  incomplete {x}")


# ---------------------------------------------------------------- check
def expand(group: str) -> tuple[list[int], list[str]]:
    nums, bad = [], []
    for part in re.split(r"\s*,\s*", group):
        if re.search(r"[-–—]", part):
            a, b = (int(x) for x in re.split(r"\s*[-–—]\s*", part))
            if a > b:
                bad.append(f"[{group}] reversed range")
                a, b = b, a
            nums.extend(range(a, b + 1))
        else:
            nums.append(int(part))
    return nums, bad


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    # 약어(et al., e.g., Fig., Eq.) 뒤에서는 자르지 않는다
    text = re.sub(r"\b(et al|e\.g|i\.e|Fig|Figs|Eq|Eqs|Ref|Refs|vs|approx|ca|No)\.",
                  lambda m: m.group(0).replace(".", "<DOT>"), text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])", text)
    out = [p.replace("<DOT>", ".").strip() for p in parts]
    return [p for p in out if len(CITE_RE.sub("", p).split()) >= 3]


def _body(text: str) -> str:
    m = REF_HEADING_RE.search(text)
    body = text[:m.start()] if m else text
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))


AUTHORYEAR_RE = re.compile(r"\([^()]*\b(19|20)\d{2}[a-z]?\)|\bet al\.?\s*\((19|20)\d{2}")


def _authoryear_cited(body: str, sources: dict, index: dict | None) -> tuple[set, list[str]]:
    """author-year 본문에서 인용된 참고문헌 번호: '(Family et al., 2019)' / 'Family et al. (2019)'.
    paper_index 가 없으면 intro_sources.json mappings 의 citations 로 대신한다."""
    if not index:
        return {n for m in sources.get("mappings", []) for n in m.get("citations", [])}, \
            ["author-year check without --index: cited set taken from mappings (not from text)"]
    cited, warn = set(), []
    for r in sources.get("references", []):
        p = index.get(r["source_file"])
        if not p:
            continue
        authors = _author_dicts(p.get("authors"))
        fam, year = (authors[0]["family"] if authors else ""), str(p.get("year", ""))
        if not (fam and year):
            warn.append(f"[{r['citation_number']}] no first-author family/year in paper_index; cannot detect")
            continue
        if re.search(rf"\b{re.escape(fam)}\b[^()\n]{{0,40}}?\(?{re.escape(year)}[a-z]?", body):
            cited.add(r["citation_number"])
    return cited, warn


def cmd_check(args):
    body = _body(read_text(args.intro))
    sources = load_json(args.sources)
    refs = sources.get("references", [])
    ref_nums = [r["citation_number"] for r in refs]
    index = {p["file"]: p for p in load_json(args.index)["papers"]} if args.index else None

    errors, warnings = [], []
    if dup := sorted({n for n in ref_nums if ref_nums.count(n) > 1}):
        errors.append(f"duplicate citation_number in references: {dup}")
    files = [r["source_file"] for r in refs]
    if dupf := sorted({f for f in files if files.count(f) > 1}):
        errors.append(f"same source_file under several numbers: {dupf}")
    if index is not None:
        if unk := sorted({f for f in files if f not in index}):
            errors.append(f"source_file not in paper_index.json: {unk}")
        bad_map = sorted({f for m in sources.get("mappings", []) for f in m.get("source_files", [])
                          if f not in index})
        if bad_map:
            errors.append(f"mapping source_files not in paper_index.json: {bad_map}")

    if args.numbered:
        order, cited = [], set()
        for g in CITE_RE.findall(body):
            nums, bad = expand(g)
            warnings.extend(bad)
            for n in nums:
                if n not in cited:
                    order.append(n)
                cited.add(n)
        if 0 in cited:
            errors.append("citation number 0 found")
        if order != sorted(order):
            errors.append(f"numbered style: first appearances not ascending: {order}")
        if order and sorted(order) != list(range(1, len(order) + 1)):
            warnings.append("numbered style: numbers are not contiguous from 1")
        cite_pat = CITE_RE
    else:
        cited, w = _authoryear_cited(body, sources, index)
        warnings.extend(w)
        order = sorted(cited)
        cite_pat = AUTHORYEAR_RE

    if missing := sorted(cited - set(ref_nums)):
        errors.append(f"cited but no reference entry: {missing}")
    if unused := sorted(set(ref_nums) - cited):
        errors.append(f"reference entries never cited: {unused}")

    sentences = split_sentences(body)
    cited_sent = [s for s in sentences if cite_pat.search(s)]
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    ratio = len(cited_sent) / len(sentences) if sentences else 0.0
    if ratio < args.min_ratio:
        warnings.append(f"citation ratio {ratio:.2f} < {args.min_ratio}")

    result = {
        "style": "numbered" if args.numbered else "authoryear",
        "sentences": len(sentences),
        "cited_sentences": len(cited_sent),
        "citation_ratio": round(ratio, 3),
        "paragraphs": len(paragraphs),
        "words": len(re.findall(r"\b\w+\b", CITE_RE.sub("", body))),
        "unique_citations": len(cited),
        "first_appearance_order": order,
        "citations_per_paragraph": [len(cite_pat.findall(p)) for p in paragraphs],
        "errors": errors,
        "warnings": warnings,
        "status": "fail" if errors else "pass",
    }
    if args.output:
        save_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if errors else 0)


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows cp949 콘솔에서 –, ₂ 등을 출력하다 중단되지 않도록
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("crossref")
    c.add_argument("--index", type=Path, required=True)
    c.add_argument("--min-similarity", type=float, default=0.90)
    c.set_defaults(func=cmd_crossref)

    r = sub.add_parser("references")
    r.add_argument("--sources", type=Path, required=True)
    r.add_argument("--index", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--style", choices=["vancouver", "authoryear"], default="vancouver")
    r.add_argument("--embed", type=Path, help="replace/append '## References' in this Introduction.md")
    r.set_defaults(func=cmd_references)

    k = sub.add_parser("check")
    k.add_argument("--intro", type=Path, required=True)
    k.add_argument("--sources", type=Path, required=True)
    k.add_argument("--output", type=Path)
    k.add_argument("--index", type=Path,
                   help="paper_index.json: flag source_files without bibliography; needed for author-year detection")
    k.add_argument("--min-ratio", type=float, default=0.70)
    k.add_argument("--numbered", action=argparse.BooleanOptionalAction, default=True)
    k.set_defaults(func=cmd_check)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
