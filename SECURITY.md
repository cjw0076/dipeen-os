# Security Policy

## 취약점 신고 (Reporting a Vulnerability)

보안 취약점은 **공개 이슈로 올리지 말고** 비공개로 알려주세요:
- 우선 경로: GitHub Security Advisory를 사용해 비공개로 보고합니다.
- 대체 경로: 프로젝트 오너에게 비공개 채널로 연락합니다.
- 48시간 내 1차 응답을 목표로 합니다.

## 핵심 보안 불변식 (dipeen 아키텍처)

dipeen은 사람과 여러 AI 에이전트가 여러 PC에서 협업하는 분산 시스템입니다. 아래 불변식은 **타협 불가**입니다.

1. **BYOK — 멤버 자격증명은 로컬에만.**
   각 팀원의 LLM 자격증명(API 키 또는 Claude 구독 세션)은 **그 사람 머신의 로컬 `.env`/세션에만** 존재합니다.
   **중앙 서버(HQ)는 멤버의 LLM 키를 절대 수신·저장·중계하지 않습니다.** HQ는 오케스트레이션(태스크 보드·라우팅·presence·채팅)만 수행합니다.

2. **구독-크레딧0 = 멤버별 개인 사용.**
   각 노드는 *자기 PC에서 자기 Claude 구독*으로 실행됩니다. 중앙 서버가 하나의 구독을 다수 사용자에게 wrap하지 않습니다(그것은 제공자 ToS 위반 소지).

3. **에이전트 실행 = 로컬 신뢰 경계.**
   `agent-client`는 사용자 머신에서 코드/셸을 실행합니다(`--dangerously-skip-permissions` 사용 시 파일·셸 접근 광범위). **신뢰하는 워크스페이스에서만** 실행하세요. 향후 커널 수준 샌드박스(Landlock / OpenShell 패턴)로 행동 반경 제한 예정.

4. **시크릿 커밋 금지.**
   `.env`, 자격증명, 토큰, `*.credentials.json`은 절대 커밋하지 마세요. `.gitignore`로 차단되어 있습니다. 노출된 키는 **즉시 로테이트**하세요.

5. **WSS 노드 인증 (로드맵).**
   원격 노드는 향후 Ed25519 challenge-response로 신원을 증명합니다(bearer 토큰 단독보다 강함). 구현 전까지 HQ는 신뢰 네트워크/팀 토큰에 의존합니다.

## Supported Versions

| Version | Supported |
|---|---|
| `main` (pre-1.0) | ✅ active |
