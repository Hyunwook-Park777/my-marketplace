# PDF Converter Plugin - Agents

## pdf-converter

MinerU 기반 범용 PDF→Markdown 변환 에이전트.

**4-Phase Pipeline:**
1. **Phase 1**: PDF 변환 (`mineru_converter.py` + `mineru4_converter.py`) — 문서별 엔진 선택(한국어→MinerU 2.x korean OCR, 그 외→4.x advanced), 출력 평탄화
2. **Phase 2**: MD 후처리 (`md_postprocessor.py`) — 헤더/표/수식 정리, 아티팩트 제거
   **Phase 2.5** (선택): 수식 번호/화살표 복원 (`equation_fixer.py`)
3. **Phase 3**: 이미지 검증 (`verify_figures.py`) — 이미지 참조 검증 + MinerU 재변환 복구
4. **Phase 4**: 품질 검증 (`verify_conversion.py`) — PDF vs MD 5개 카테고리 0~100점 채점

**Tools**: Read, Write, Glob, Grep, Bash, Edit

**Requirements**: CUDA GPU, MinerU 2.x (기본 Python), MinerU 4.x (별도 venv `~/venvs/mineru4`, 선택), PyMuPDF
