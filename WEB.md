# CLASSY 웹

운영 주소: https://classystudy.com/

독립 React 프론트엔드는 [`web/`](web/)에 있습니다. 기존 Flutter의 보라색·Pretendard·아이콘·간격을 유지하고 데스크톱과 모바일 브라우저를 지원합니다.

```sh
cd web
npm ci
npm run build
npm start
```

웹에서 `/api/`를 기존 Django에 프록시하므로 별도 사용자·캐시·강의 DB를 만들지 않습니다. Django 변경은 판매 중인 강의 목록의 비로그인 조회 허용이며, 스트리밍·결제·업로드에는 기존 인증·권한을 적용합니다.

- [기능 및 실행·테스트](web/README.md)
- [앱 디자인 대응](web/DESIGN.md)
- [AWS 배포 및 복구](web/DEPLOYMENT.md)

웹 PG 충전은 사업자 PG 계약·운영 키가 필요해 미연동입니다. 기존 스토어 구매 검증·원장·환불 로직은 변경하지 않습니다.
