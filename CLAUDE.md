# 작업 규칙

- 변경사항은 작업 브랜치에서 커밋·푸시하고 PR을 만든 뒤, CI(`test`)가 통과하고 충돌·미해결 리뷰가 없으면 **확인을 묻지 않고 바로 main에 병합**한다.
- 리뷰 봇(Codex 등) 지적이 실제 결함이면 고쳐서 푸시한 뒤 병합한다.
- 병합 전 로컬에서 `python -m pytest -q tests`와 `node --test tests/js/*.test.mjs`를 돌린다.
