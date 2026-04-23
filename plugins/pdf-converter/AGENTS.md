# PDF Converter Plugin - Agents

## pdf-converter

MinerU 기반 범용 PDF→Markdown 변환 에이전트.

**4-Phase Pipeline:**
1. **Phase 1**: PDF 변환 (`mineru_converter.py`) — MinerU CLI로 PDF→MD 변환, 출력 평탄화
2. **Phase 2**: MD 후처리 (`md_postprocessor.py`) — 헤더/표/수식 정리, 아티팩트 제거
3. **Phase 3**: 이미지 검증 (`verify_figures.py`) — 이미지 참조 검증 + MinerU 재변환 복구
4. **Phase 4**: 품질 검증 (`verify_conversion.py`) — PDF vs MD 5개 카테고리 0~100점 채점

**Tools**: Read, Write, Glob, Grep, Bash, Edit

**Requirements**: MinerU (`pip install "mineru[all]"`), PyMuPDF (`pip install pymupdf`)
