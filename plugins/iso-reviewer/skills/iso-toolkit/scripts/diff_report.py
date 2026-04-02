#!/usr/bin/env python3
"""
ISO Document Diff Report Generator

두 ISO 문서의 파싱 결과(JSON)를 비교하여 Markdown 변경사항 보고서를 생성합니다.

Usage:
    python diff_report.py <is_parsed.json> <dis_parsed.json> -o <report.md>
    python diff_report.py <is_parsed.json> <dis_parsed.json>  # stdout 출력

변경 유형:
    - ADDED: DIS에만 존재하는 신설 조항
    - REMOVED: IS에만 존재하는 삭제 조항
    - MODIFIED: 양쪽 모두 존재하나 내용이 변경된 조항
    - RENUMBERED: 제목이 동일하나 번호가 변경된 조항
    - UNCHANGED: 변경 없는 조항
"""

import argparse
import json
import sys
from collections import OrderedDict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


def load_parsed(json_path: str) -> dict:
    """파싱된 JSON을 로드"""
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {json_path}")
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def normalize_content(text: str) -> str:
    """비교를 위한 텍스트 정규화: 공백/줄바꿈 통일"""
    import re
    text = re.sub(r'\s+', ' ', text.strip())
    text = text.lower()
    return text


def similarity_ratio(a: str, b: str) -> float:
    """두 텍스트의 유사도 (0.0 ~ 1.0)"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, normalize_content(a), normalize_content(b)).ratio()


def find_renumbered(is_clauses: dict, dis_clauses: dict) -> dict:
    """
    번호가 변경된 조항을 감지.
    IS에만 있는 조항의 제목과 DIS에만 있는 조항의 제목을 비교.

    Returns:
        { is_number: dis_number } 매핑
    """
    is_only = {n: c for n, c in is_clauses.items() if n not in dis_clauses}
    dis_only = {n: c for n, c in dis_clauses.items() if n not in is_clauses}

    renumbered = {}
    used_dis = set()

    for is_num, is_clause in is_only.items():
        is_title = normalize_content(is_clause['title'])
        best_match = None
        best_ratio = 0.0

        for dis_num, dis_clause in dis_only.items():
            if dis_num in used_dis:
                continue
            dis_title = normalize_content(dis_clause['title'])
            ratio = SequenceMatcher(None, is_title, dis_title).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = dis_num

        # 제목 유사도 80% 이상이면 번호 변경으로 판단
        if best_match and best_ratio >= 0.8:
            renumbered[is_num] = best_match
            used_dis.add(best_match)

    return renumbered


def compare_clauses(is_data: dict, dis_data: dict) -> dict:
    """
    두 문서의 조항을 비교하여 변경사항을 분류.

    Returns:
        {
            "is_document": str,
            "dis_document": str,
            "summary": { "added": int, "removed": int, "modified": int, "renumbered": int, "unchanged": int },
            "changes": [
                {
                    "type": "ADDED|REMOVED|MODIFIED|RENUMBERED|UNCHANGED",
                    "clause_number": str,
                    "title": str,
                    "is_content": str,   (MODIFIED, REMOVED)
                    "dis_content": str,  (MODIFIED, ADDED)
                    "old_number": str,   (RENUMBERED)
                    "new_number": str,   (RENUMBERED)
                    "similarity": float, (MODIFIED)
                    "content_diff": str, (MODIFIED - 주요 변경 내용 요약)
                }
            ]
        }
    """
    is_clauses = {c['number']: c for c in is_data.get('clauses', [])}
    dis_clauses = {c['number']: c for c in dis_data.get('clauses', [])}

    # 번호 변경 감지
    renumbered_map = find_renumbered(is_clauses, dis_clauses)
    renumbered_is_nums = set(renumbered_map.keys())
    renumbered_dis_nums = set(renumbered_map.values())

    changes = []
    summary = {"added": 0, "removed": 0, "modified": 0, "renumbered": 0, "unchanged": 0}

    # 모든 조항 번호 수집 (정렬)
    all_numbers = sorted(
        set(is_clauses.keys()) | set(dis_clauses.keys()),
        key=clause_sort_key
    )

    for num in all_numbers:
        in_is = num in is_clauses
        in_dis = num in dis_clauses

        # 번호 변경된 조항은 별도 처리
        if num in renumbered_is_nums:
            new_num = renumbered_map[num]
            changes.append({
                "type": "RENUMBERED",
                "clause_number": num,
                "title": is_clauses[num]['title'],
                "old_number": num,
                "new_number": new_num,
                "is_content": is_clauses[num].get('content', ''),
                "dis_content": dis_clauses[new_num].get('content', ''),
                "similarity": similarity_ratio(
                    is_clauses[num].get('content', ''),
                    dis_clauses[new_num].get('content', '')
                ),
            })
            summary["renumbered"] += 1
            continue

        if num in renumbered_dis_nums:
            # 이미 RENUMBERED로 처리됨
            continue

        if in_is and in_dis:
            # 양쪽 모두 존재: 내용 비교
            is_content = is_clauses[num].get('content', '')
            dis_content = dis_clauses[num].get('content', '')
            sim = similarity_ratio(is_content, dis_content)

            if sim >= 0.95:
                changes.append({
                    "type": "UNCHANGED",
                    "clause_number": num,
                    "title": dis_clauses[num]['title'],
                    "similarity": sim,
                })
                summary["unchanged"] += 1
            else:
                changes.append({
                    "type": "MODIFIED",
                    "clause_number": num,
                    "title": dis_clauses[num]['title'],
                    "is_content": is_content,
                    "dis_content": dis_content,
                    "similarity": sim,
                })
                summary["modified"] += 1

        elif in_dis and not in_is:
            changes.append({
                "type": "ADDED",
                "clause_number": num,
                "title": dis_clauses[num]['title'],
                "dis_content": dis_clauses[num].get('content', ''),
            })
            summary["added"] += 1

        elif in_is and not in_dis:
            changes.append({
                "type": "REMOVED",
                "clause_number": num,
                "title": is_clauses[num]['title'],
                "is_content": is_clauses[num].get('content', ''),
            })
            summary["removed"] += 1

    return {
        "is_document": is_data.get('document_title', 'Unknown'),
        "dis_document": dis_data.get('document_title', 'Unknown'),
        "is_total_clauses": is_data.get('total_clauses', 0),
        "dis_total_clauses": dis_data.get('total_clauses', 0),
        "summary": summary,
        "changes": changes,
    }


def clause_sort_key(number: str) -> tuple:
    """조항 번호를 정렬 가능한 키로 변환. 숫자 → 알파벳(부속서) 순"""
    parts = number.split('.')
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p), ''))  # 숫자 조항
        elif p.isalpha():
            result.append((1, 0, p))         # 부속서 (숫자 뒤에 정렬)
        else:
            try:
                result.append((0, int(p), ''))
            except ValueError:
                result.append((1, 0, p))
    return tuple(result)


def generate_markdown_report(comparison: dict) -> str:
    """비교 결과를 Markdown 보고서로 변환"""
    lines = []
    summary = comparison['summary']

    # 헤더
    lines.append(f"# ISO 문서 변경사항 분석 보고서")
    lines.append("")
    lines.append(f"**생성일**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**기존 문서 (IS)**: {comparison['is_document']}")
    lines.append(f"**신규 문서 (DIS)**: {comparison['dis_document']}")
    lines.append("")

    # 요약 통계
    lines.append("## 변경 요약")
    lines.append("")
    lines.append(f"| 구분 | 조항 수 |")
    lines.append(f"|------|---------|")
    lines.append(f"| IS 전체 조항 수 | {comparison['is_total_clauses']} |")
    lines.append(f"| DIS 전체 조항 수 | {comparison['dis_total_clauses']} |")
    lines.append(f"| 신설 (Added) | {summary['added']} |")
    lines.append(f"| 삭제 (Removed) | {summary['removed']} |")
    lines.append(f"| 수정 (Modified) | {summary['modified']} |")
    lines.append(f"| 번호 변경 (Renumbered) | {summary['renumbered']} |")
    lines.append(f"| 변경 없음 (Unchanged) | {summary['unchanged']} |")
    lines.append("")

    total_changes = summary['added'] + summary['removed'] + summary['modified'] + summary['renumbered']
    total = total_changes + summary['unchanged']
    if total > 0:
        change_rate = (total_changes / total) * 100
        lines.append(f"**변경률**: {change_rate:.1f}% ({total_changes}/{total} 조항)")
        lines.append("")

    # 신설 조항
    added = [c for c in comparison['changes'] if c['type'] == 'ADDED']
    if added:
        lines.append("## 신설 조항 (Added)")
        lines.append("")
        for c in added:
            lines.append(f"### {c['clause_number']} {c['title']}")
            lines.append("")
            content = c.get('dis_content', '').strip()
            if content:
                # 내용 미리보기 (500자 제한)
                preview = content[:500] + ('...' if len(content) > 500 else '')
                lines.append(f"> {preview}")
                lines.append("")

    # 삭제 조항
    removed = [c for c in comparison['changes'] if c['type'] == 'REMOVED']
    if removed:
        lines.append("## 삭제 조항 (Removed)")
        lines.append("")
        for c in removed:
            lines.append(f"### ~~{c['clause_number']} {c['title']}~~")
            lines.append("")
            content = c.get('is_content', '').strip()
            if content:
                preview = content[:500] + ('...' if len(content) > 500 else '')
                lines.append(f"> {preview}")
                lines.append("")

    # 수정 조항
    modified = [c for c in comparison['changes'] if c['type'] == 'MODIFIED']
    if modified:
        # 유사도가 낮은 순 (변경이 큰 순)으로 정렬
        modified.sort(key=lambda c: c.get('similarity', 1.0))
        lines.append("## 수정 조항 (Modified)")
        lines.append("")
        for c in modified:
            sim = c.get('similarity', 0)
            change_level = "경미" if sim >= 0.8 else "보통" if sim >= 0.5 else "대폭"
            lines.append(f"### {c['clause_number']} {c['title']}")
            lines.append(f"- **변경 수준**: {change_level} (유사도 {sim:.0%})")
            lines.append("")
            lines.append("**IS 버전:**")
            is_preview = c.get('is_content', '').strip()[:500]
            if is_preview:
                lines.append(f"> {is_preview}")
            lines.append("")
            lines.append("**DIS 버전:**")
            dis_preview = c.get('dis_content', '').strip()[:500]
            if dis_preview:
                lines.append(f"> {dis_preview}")
            lines.append("")

    # 번호 변경 조항
    renumbered = [c for c in comparison['changes'] if c['type'] == 'RENUMBERED']
    if renumbered:
        lines.append("## 번호 변경 조항 (Renumbered)")
        lines.append("")
        lines.append("| IS 번호 | DIS 번호 | 제목 | 내용 유사도 |")
        lines.append("|---------|---------|------|-----------|")
        for c in renumbered:
            sim = c.get('similarity', 0)
            lines.append(f"| {c['old_number']} | {c['new_number']} | {c['title']} | {sim:.0%} |")
        lines.append("")

    # 변경 없는 조항 (접힌 상태로)
    unchanged = [c for c in comparison['changes'] if c['type'] == 'UNCHANGED']
    if unchanged:
        lines.append("## 변경 없는 조항 (Unchanged)")
        lines.append("")
        lines.append(f"총 {len(unchanged)}개 조항이 변경 없음:")
        lines.append("")
        for c in unchanged:
            lines.append(f"- {c['clause_number']} {c['title']}")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='ISO 문서 비교 보고서 생성'
    )
    parser.add_argument('is_json', help='IS(기존) 버전 파싱 JSON 경로')
    parser.add_argument('dis_json', help='DIS(신규) 버전 파싱 JSON 경로')
    parser.add_argument('-o', '--output', help='출력 Markdown 파일 경로')
    parser.add_argument('--json-output', help='비교 결과 JSON 저장 경로')

    args = parser.parse_args()

    try:
        is_data = load_parsed(args.is_json)
        dis_data = load_parsed(args.dis_json)

        comparison = compare_clauses(is_data, dis_data)
        report_md = generate_markdown_report(comparison)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report_md, encoding='utf-8')
            print(f"보고서 생성 완료: {args.output}")
        else:
            print(report_md)

        if args.json_output:
            json_path = Path(args.json_output)
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps(comparison, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"비교 JSON 저장: {args.json_output}")

        # 요약 출력
        s = comparison['summary']
        total = s['added'] + s['removed'] + s['modified'] + s['renumbered']
        print(f"\n변경 요약: 신설 {s['added']} | 삭제 {s['removed']} | "
              f"수정 {s['modified']} | 번호변경 {s['renumbered']} | "
              f"변경없음 {s['unchanged']} | 총 변경 {total}건")

    except Exception as e:
        print(f"에러: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
