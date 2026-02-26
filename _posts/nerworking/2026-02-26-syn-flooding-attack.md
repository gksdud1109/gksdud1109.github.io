---
title: "[네트워킹]DoS/DDoS 공격 총정리 - SYN Flooding부터 Bcrypt DoS까지"
date: 2026-02-26 14:00:00 +0900
categories: [CS]
tags: [networking, tcp, security, ddos, syn-flooding, slowloris, quic, http2, bcrypt]
---

TCP/UDP/HTTP 연결 과정을 악용한 대표적인 DoS/DDoS 공격 기법들을 정리한다. SYN Flooding, TCP Connection Flood, Slowloris부터 QUIC Initial Packet Flood, HTTP/2 Rapid Reset, Bcrypt DoS까지 다룬다.

---

## SYN Flooding

https://datatracker.ietf.org/doc/html/rfc4987

공격자가 3-Way Handshake의 3번째 단계인 ACK를 보내지 않고 수많은 SYN만 보내 서버의 연결 자원(메모리)를 고갈시키는 공격이다.

### 공격 원리

TCP 3-Way Handshake의 정상적인 흐름:

1. 클라이언트 → 서버: SYN
2. 서버 → 클라이언트: SYN-ACK (서버가 메모리 할당하고 대기)
3. 클라이언트 → 서버: ACK (연결 완료)

SYN Flooding에서는 공격자가 1번만 수없이 보내고 3번을 보내지 않는다. 서버는 2번 단계에서 메모리를 할당하고 ACK를 기다리는 반쯤 열린(Half-open) 상태로 대기하게 되는데, 이런 연결이 수만 개 쌓이면 서버의 연결 자원이 고갈된다.

### 방어 기법: SYN Cookies

서버가 상태를 메모리에 저장하지 않고 해시로 계산해 변환하는 SYN 쿠키(SYN Cookies) 기법이 널리 사용된다.

**기존 방식:**

```
SYN 받음 → 서버 메모리 할당, 연결 준비 → SYN-ACK 보냄 → 대기
```

**SYN 쿠키 방식:**

```
SYN 받음 → 메모리 할당 안함 → 클라이언트 IP, port num 등을 서버만 아는 비밀키와 섞어
복잡한 해시값(SYN 쿠키)를 만듦 → 이 값을 서버의 ISN(server_isn)으로 삼아 SYN-ACK 보냄
→ 서버는 해당 연결을 잊어버림
```

이렇게 하면 ACK를 받았을 때 클라이언트의 패킷에 담긴 `server_isn + 1`에 담긴 해시값과 대조해서 검증이 가능하다. 메모리를 할당하지 않으므로 Half-open 상태가 쌓이지 않는다.

### 패킷이 탈취되면 소용 없는 것 아닌가?

**공격자는 가짜 IP를 사용한다 (IP Spoofing):**
- 공격자가 자신의 진짜 IP로 수만 개의 SYN을 보내면 서버 방화벽에 즉시 차단된다
- 그래서 존재하지 않거나 남의 IP로 위장해서 SYN을 보내야 함

**답장이 엉뚱한 곳으로 간다:**
- 서버는 가짜 IP를 향해 SYN-ACK(SYN 쿠키가 담긴)를 보낸다
- 따라서 공격자는 자신에게 오지 않는 패킷의 번호를 가로채기(Sniffing)가 매우 어려움

**공격의 목적:**
- 공격자가 패킷을 가로채서 마지막 ACK까지 꼬박꼬박 보낸다면, 서버는 정상적으로 연결을 맺는다
- 이건 더 이상 SYN 패킷만 보내서 반쯤 열린(Half-open) 상태를 만드는 SYN Flooding 공격이 아님
- → 이런 경우는 TCP Connection Flood

**공격자의 손해:**
- 진짜 IP를 썼기 때문에 서버의 방화벽(IPS/IDS)에서 해당 IP를 찾아내어 영구 차단하면 공격이 끝남
- 또한 공격자의 컴퓨팅 자원도 고갈되기 쉬움

---

## TCP Connection Flood

공격자가 진짜 여러 PC를 조작해서 ACK까지 정상적으로 맞춰서 보낼 수 있다면 어떨까?

공격자가 수만 대의 좀비 PC(봇넷)를 조종해서 진짜로 3-Way Handshake를 끝까지(Full Connection) 맺어버리는 방식의 공격이다.

가게에 들어와 아무것도 안 시키고 전부 자리만 차지하고 있는 진상 손님들인 셈이다.

### 방어 기법

이러한 상황에서는 네트워크 계층(L4)을 넘어서 더 똑똑한 방어법이 필요해진다.

### 1. 연결 임계치 및 타임아웃 조절 (Rate Limiting)

서버 앞단의 방화벽이나 로드밸런서(L4 스위치 등)에서 깐깐한 규칙을 세운다.

- **IP당 연결 수 제한**: 단일 IP에서 요청할 수 있는 연결 수에 제한을 두고 비정상으로 판단될 시 차단한다
- **타임아웃 줄이기**: 좀비 PC들은 보통 연결만 맺어두고 서버 자원을 점유하기 위해 가만히(Idle) 있는 경우가 많음. 연결을 맺고 이처럼 Idle하게 있는 경우 타임아웃을 줄여 메모리를 빨리 회수할 수 있다

### 2. 행위 기반 분석 및 웹 방화벽 (WAF)

연결 자체는 정상이어도 진짜 사람인지, 기계(봇)인지를 구별해 내는 방식이다.

- Cloudflare 같은 방어 서비스를 거칠 때 "사람인지 확인 중입니다" 같은 로딩 화면이나 그림 맞추기(CAPTCHA)가 뜨는 경우가 해당된다
- 단순한 좀비 PC 프로그램은 브라우저처럼 JS를 실행하거나 그림을 맞추지 못하기 때문에 여기서 다 걸러진다

### 3. 분산 방어 (CDN 및 대규모 트래픽 수용)

좀비 PC가 10만 대 단위로 밀고 들어오면 앞선 대책들이 있더라도 서버 혼자 감당하기 불가능하다.

그래서 전 세계에 흩어져 있는 거대한 CDN(Content Delivery Network) 서버들을 방패막이로 세운다.

- 공격 트래픽이 들어오면 한 곳(우리 서버)으로 쏠리지 않게 전 세계의 방어 서버들이 트래픽을 나눠서 흡수
- 정상적인 요청만 진짜 서버로 넘겨주는 방식

### 4. 헤드리스 브라우저 / AI와 캡챠 팜 / Origin 서버 직접 타격

공격자가 진짜 사람처럼 행동하는 프로그램을 만들거나 CDN을 우회할 수 있다.

- **헤드리스 브라우저(Headless Browser) 악용**: 화면만 없을 뿐 실제 크롬과 똑같이 작동하는 프로그램을 써서 자바스크립트를 정상적으로 실행하고 방화벽을 속일 수 있다.
- **AI와 캡챠 팜(CAPTCHA Farm)**: AI의 이미지 인식 기술로 그림맞추기(CAPTCHA)를 자동으로 풀어버리거나, 심지어 제3세계의 저임금 노동자들을 수백 명 고용해서 사람의 손으로 캡챠만 하루 종일 풀게 하는 공장(Farm)을 돌리기도 한다.
- **오리진 서버(Origin IP) 직접 타격**: 방어막인 CDN을 뚫는 게 아니라, CDN 뒤에 숨어있는 진짜 서버의 IP를 어떻게든 알아낼 수 있다면 CDN을 우회해서 다이렉트로 타격을 줄 수 있음

**방어자: 행동 감식으로 방어**

- **행동 생체 인식(Behavioral Biometrics)**: 마우스 움직임, 스크롤 속도, 클릭하기까지의 대기 시간 등을 AI가 분석한다. 사람은 마우스를 움직일 때 미세하게 떨리거나 곡선을 그리지만, 봇은 너무 완벽한 직선으로 움직이거나 프로그래밍된 어색한 패턴을 보인다.
- **브라우저 지문 인식(Browser Fingerprinting)**: 겉으로는 정상적인 크롬 브라우저라고 주장하지만, 방어 시스템이 더 깊은 곳을 찔러본다. 그래픽 카드(GPU)로 연산해야 하는 복잡한 3D 도형 렌더링을 요구하는 식의 감식. 가짜 브라우저나 저사양 봇넷은 진짜 PC의 그래픽 카드가 만들어내는 미세한 픽셀 차이를 구현하지 못해 가짜임이 탄로난다.
- **오리진 은폐 기술(Origin Cloaking & 터널링)**: 해커가 진짜 서버 IP를 찾지 못하도록, 아예 서버가 인터넷에 직접 연결되지 않고 CDN 내부망(터널)을 통해서만 통신하도록 원천 봉쇄해버리는 방식이다.

---

## Slowloris 공격

수만 대의 PC를 동원하지 않고 서버를 죽이는 방식도 존재한다. 데이터를 아주 찔끔찔끔, 1초에 1바이트씩 엄청나게 느리게 지속적으로 보내는 방식. 서버는 계속 연결을 유지하려다 메모리가 꽉 차서 말라 죽게 된다. 정상적인 '느린 인터넷을 쓰는 사람'처럼 위장한 것.

### 1. 웹 서버의 착한 습성 악용

웹 서버는 클라이언트가 인터넷 환경이 안 좋아서 데이터를 천천히 보내더라도, 요청을 끝마칠 때까지 연결을 끊지 않고 기다려준다. 슬로로리스(Slow Loris, 늘보 로리스)는 이를 이용한 공격이다.

### 2. 공격 진행 과정 (끝나지 않는 대화)

- **정상적인 연결**: 공격자는 TCP 3-Way Handshake를 정상적으로 맺어 완벽한 정상 사용자로 위장
- **요청 쪼개 보내기**: 웹 브라우저가 서버에 웹페이지를 달라고 요청할 때는 "나 할 말 다했음"의 의미로 빈 줄(엔터 두 번, CRLF)을 보낸다. 슬로로리스는 이걸 절대 안 침.
- **숨통 연장하기**: 서버가 타임아웃을 시키려고 할 때쯤, `X-a: b` 같은 아무 의미 없는 헤더 데이터들을 지속해서 보낸다.
- **메모리(스레드) 고갈**: 서버는 앞선 HTTP 요청 연결의 특성상 계속해서 메모리(Thread) 한 켠을 열고 요청이 끝나기를 기다린다.

### 3. 방어

- **타임아웃 조절**: 연결 후 timeout이 발생하는 상한선을 조절한다.
- **최소 전송 속도 제한**: 1초에 500바이트 등의 최소 전송 속도 제한을 설정한다.
- **아키텍처 변경**: 클라이언트 연결 하나에 요청 스레드 하나를 계속 비워두고 연결을 유지하는 구형 서버(예: Apache의 특정 모드) 대신, 비동기 방식의 서버(예: Nginx)를 앞단에 두어 대기 상태 자체를 무력화시킴.

---

## QUIC에서의 공격

### 1. SYN Flooding의 QUIC 버전: Initial Packet Flood 공격

QUIC은 연결을 맺자마자 암호화(TLS 1.3) 세팅까지 한 번에 끝낸다. 연결 속도는 빠르지만, 암호화 통신을 준비하는 과정은 서버의 CPU와 메모리를 굉장히 많이 소모한다. 서버 JWT 로그인 처리 시에 토큰 암호화 연산을 위해 CPU를 소모하는 것처럼!

**공격자의 우회법:**
- 공격자는 가짜 IP를 달고 서버에 수만 개의 Initial 패킷(QUIC의 첫 인사)을 던진다
- 서버가 암호화 키를 계산하느라 CPU가 뻗어버리게 만든다
- TCP의 SYN Flooding보다 훨씬 더 치명적일 수 있음

**QUIC의 방어법 (QUIC판 SYN 쿠키 - Retry Token):**
- 가짜 IP 공격이 감지되면 서버는 암호화 계산을 시작하지 않고, Retry 패킷이라는 걸 보낸다
- 클라이언트가 송신한 IP로 암호화된 토큰을 보내면 가짜 IP를 쓴 공격자는 이 토큰을 받을 수 없어 다음 단계로 넘어가지 못하고 차단된다

### 2. 증폭 공격 (Amplification Attack)

공격자가 아주 작은 10바이트짜리 패킷을 서버에 보내면, QUIC을 쓰는 서버는 암호화 인증서 등의 여러 복잡한 정보가 담긴 3,000바이트짜리 답장을 해야 한다. 공격자는 10을 써서 서버의 3,000짜리 자원 소모를 이끌어냈다.

**방어법 (3배수 제한 규칙):**
- QUIC 표준에는 "주소가 확실히 검증되기 전까지, 서버의 답장 크기는 클라이언트가 보낸 데이터 크기의 3배를 넘을 수 없다"는 강력한 룰이 지정되어 있다
- 증폭 공격을 원천 차단한 설계

### 3. 스트림 다중화를 이용한 대역폭/자원 고갈 공격

**공격자의 우회법 (QUIC Stream Flood):**
- QUIC의 장점은 하나의 연결로도 그 안에서 스트림을 다중화하여 여러 데이터 통로를 동시에 개설할 수 있다
- 공격자는 이 정상 연결 1개 안에서 수만 개의 텅 빈 스트림을 동시에 열거나, 아주 무거운 영상 데이터를 요청하는 스트림을 다수 열어 네트워크 대역폭(Bandwidth)과 서버 메모리를 고갈시킨다 (HTTP/2 Rapid Reset과 유사)

**방어법 (할당량 통제 - Flow Control):**
- QUIC은 클라이언트를 믿지 않도록 설계되었다. 서버는 연결을 맺을 때부터 강력한 제한 프레임(Limit Frame)을 건다
- `MAX_STREAMS`: 한 번에 열 수 있는 스트림 개수 제한, 초과 시 강제 종료
- `MAX_DATA`: 한 번에 전송해 줄 수 있는 스트림 용량 제한

---

## HTTP/2 Rapid Reset (CVE-2023-44487)

QUIC에서 언급되었던 스트림 다중화를 악용한 공격과 유사한 것이 2023년 구글, AWS, 클라우드플레어 등의 글로벌 클라우드 기업들이 동시에 역사상 최대 규모의 DDoS 공격을 받은 `HTTP/2 Rapid Reset` 공격이다.

### 1. HTTP/2의 양날의 검: 다중화와 취소

HTTP/2는 속도를 높이기 위해 한 번 맺은 연결(TCP 커넥션) 안에서 여러 개의 스트림을 동시에 열 수 있는 다중화 기술을 도입했다.

이때 효율성을 위해 클라이언트에게 부여한 권한이 `RST_STREAM`(Reset Stream, 스트림 취소) 프레임이다. 필요 없어진 이미지/영상 파일 등의 스트림 연결을 클라이언트 측에서 취소할 수 있게 함으로써, 불필요한 대역폭 낭비를 방지하는 기능이었다.

### 2. 공격자의 악용: 스트림 열고 취소하기 무한반복

공격자는 서버가 동시에 여러 스트림을 열게 해준다는 점과, `RST_STREAM`으로 즉시 취소할 수 있다는 점을 악용해 공격한다.

- **요청(Open)**: 공격자가 서버에 무거운 작업(예: DB 조회, 복잡한 렌더링 등)을 요청하는 스트림을 연다
- **취소(Reset)**: 서버가 막 요청을 받아들여 CPU와 메모리를 쓰며 작업을 시작하려는 찰나, 0.001초 만에 `RST_STREAM`을 보내 "아까 그거 취소함!" 이렇게 던진다
- **무한 반복(Rapid Reset)**: 취소를 했으니 공격자는 응답을 받을 필요가 없어져 네트워크 대역폭을 전혀 쓰지 않는다. 대신 취소하자마자 빈자리에 이어서 새로운 요청을 보낸다. 이걸 하나의 연결 안에서 1초에 수십만 번 반복한다

### 3. 방어가 뚫린 이유

기존의 방어 체계는 하나의 클라이언트 IP에서 유지하고 있는 연결 수, 다운받고 있는 데이터 양을 기준으로 공격을 차단했다.

하지만 Rapid Reset 공격은 단 1개의 연결만 맺고, 데이터도 다운받지 않은 채 내부 스트림만 엄청난 속도로 켰다 껐다를 반복했기 때문에 기존 방화벽들이 정상적인 1명의 사용자로 착각하고 통과시켰다.

### 4. 현재의 대응 방식

글로벌 클라우드 기업들이 긴급 패치를 적용했다.

**비율 추적 (Rate Limiting on Resets):**
- 요청을 하는 건 자유롭게 하되, 요청 대비 취소(`RST_STREAM`) 비율이 비정상적으로 높거나 그 속도가 너무 빠르면 커넥션을 악성으로 간주하고 즉시 끊어버린다

---

## 비대칭 자원 소모 공격 - Bcrypt DoS / Crypto DoS

앞선 HTTP/2 Rapid Reset, QUIC에서의 취약점과 비슷한 방식으로 Spring 애플리케이션 레벨에서 널리 사용되는 Bcrypt(사용자의 비밀번호 검증/해싱), JWT(토큰의 서명 및 검증/HMAC, RSA 등)의 로직은 공통적으로 서버의 CPU 자원 소모량이 많다.

이러한 취약점을 보안 용어로 비대칭 자원 소모 공격(Asymmetric Resource Consumption) 또는 Bcrypt DoS / Crypto DoS라고 부른다.

### 1. Bcrypt의 특성

Bcrypt는 태생부터 공격자의 비밀번호 무작위 대입(Brute-force)를 막기 위해, 계산하는 데 엄청나게 오랜 시간이 걸리게 만들려는 취지로 설계되었다. 내부적으로 Work Factor(Cost)라는 설정값이 있어서, 이 값을 높일수록 해싱 연산이 기하급수적으로 느려진다.

### 2. Bcrypt DoS 공격

- **요청 (비용 거의 0)**: 공격자는 가짜 아이디와 엄청나게 긴 무작위 문자열을 비밀번호로, Spring Boot 서버의 `/login` 엔드포인트에 로그인 요청을 1초에 수천 번 쏟아낸다
- **연산 (비용 엄청남)**: Spring Boot의 `PasswordEncoder`(Bcrypt)는 이 가짜 비밀번호가 맞는지 확인하기 위해 CPU 자원을 소모해 해싱 연산을 시작한다. 보통 비밀번호 하나를 검증하는 데 0.1초~0.5초 정도 걸리게 맞춰두는데, 수천 개의 요청이 몰리면 서버의 스레드 풀이 꽉 차고 CPU가 터져버림
- **결과**: 실제 정상 사용자는 로그인을 할 수 없고, 서버에서 돌아가던 다른 API까지 모조리 마비

> JWT 서명 검증 역시 동일. 공격자가 조작된 무거운 토큰을 수만 개 던지면, Spring Security 필터 단에서 서명을 수학적으로 검증하느라 CPU 자원 소모

### 3. Spring Boot 환경에서의 방어 전략

공격 시에 완전히 정상적인 HTTP POST 요청(로그인) 형태를 띄고 있어, 앞서 다룬 단순 방화벽(L4)만으로는 막기가 까다롭다. 애플리케이션 단에서 대책이 필요하다.

- **API 속도 제한 (Rate Limiting)**: 동일 IP나 사용자 식별자를 기준으로 시간당 로그인 시도 제한 횟수를 두도록 해야 한다. Spring 환경에서는 보통 Redis나 Bucket4j 같은 라이브러리를 조합해 로그인 엔드포인트 앞단에 방어막(Interceptor/Filter)을 친다
- **입력값 길이 제한 (Validation)**: 해시 연산은 입력값이 길수록 더 많은 CPU를 먹는다. DTO 단계에서 `@Size(max=64)` 처럼 비밀번호 최대 길이를 엄격하게 잘라야 한다
- **WAF 및 CAPTCHA 도입**: 동일 IP 제한을 피하기 위해 봇넷이 여러 IP로 분산 공격을 한다면, 앞서 다루었던 Nginx나 Cloudflare(WAF) 단에서 1차로 걸러내거나, 로그인 창에 CAPTCHA를 띄워 자동화된 스크립트의 접근을 막아야 한다

### 4. Redis/Bucket4j를 활용한 Rate Limiting 예시 코드

요청 흐름: `클라이언트 요청 → RateLimitFilter → Spring Security 로그인 처리(Bcrypt) → 컨트롤러`

**핵심 로직: 로그인 요청 제한 필터 구현**

Spring Security의 로그인 필터가 작동하기 전에 IP를 확인하고 허용량을 넘으면 쳐내는 Filter:

```java
public class LoginRateLimitFilter extends OncePerRequestFilter {

    private final LettuceBasedProxyManager proxyManager; // Redis와 통신하는 매니저

    public LoginRateLimitFilter(LettuceBasedProxyManager proxyManager) {
        this.proxyManager = proxyManager;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        // 1. 타겟 설정: /login 엔드포인트에 대한 POST 요청만 검사
        if (request.getRequestURI().equals("/login") && request.getMethod().equalsIgnoreCase("POST")) {

            // 2. 식별자 추출: 클라이언트의 IP를 가져온다 (프록시나 로드밸런서를 거친다면 X-Forwarded-For 헤더 확인 필요)
            String clientIp = request.getRemoteAddr();
            String bucketKey = "login_rate_limit:" + clientIp;

            // 3. 버킷 설정: Redis에서 해당 IP의 버킷을 가져오거나, 없으면 새로 만듦
            Bucket bucket = proxyManager.builder().build(bucketKey, this::getConfig);

            // 4. 요청 권한 확인 (토큰 1개 소모)
            if (bucket.tryConsume(1)) {
                // 권한이 있으면 다음 필터(Spring Security)로 통과
                filterChain.doFilter(request, response);
            } else {
                // 권한이 없으면(제한 초과) 429 Too Many Requests 에러 반환 (Bcrypt 연산 아예 안 함!)
                response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
                response.getWriter().write("Too many login attempts. Please try again later.");
                return;
            }
        } else {
            // 로그인 요청이 아니면 그냥 통과
            filterChain.doFilter(request, response);
        }
    }

    // 버킷 정책: 최대 5개를 담을 수 있고, 1분마다 5개씩 꽉 채워줌
    private BucketConfiguration getConfig() {
        Refill refill = Refill.greedy(5, Duration.ofMinutes(1));
        Bandwidth limit = Bandwidth.classic(5, refill);
        return BucketConfiguration.builder().addLimit(limit).build();
    }
}
```

**Security 설정에 필터 끼워 넣기:**

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Autowired
    private LettuceBasedProxyManager proxyManager;

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            // ... 기존 설정들 ...
            // 무거운 로그인 필터가 돌기 '전'에 우리가 만든 RateLimitFilter를 먼저 실행
            .addFilterBefore(new LoginRateLimitFilter(proxyManager), UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
```

이렇게 하면 공격자가 악성 로그인 요청을 보내더라도, 딱 첫 5번만 Bcrypt 연산을 수행하고, 나머지 다량의 요청들은 Redis 조회만 거친 뒤 `429 (Too Many Requests)` 등으로 빠르게 튕겨낼 수 있다.

실제 현업에서는 이러한 코드에 더해, 실패 횟수가 일정 이상 넘어가면 계정을 임시로 잠가버리거나(Account Lock), 보안팀 슬랙으로 알림을 보내는 로직을 추가하기도 한다.

---

## 비교 정리

### TCP/HTTP 기반 공격

| 구분 | SYN Flooding | TCP Connection Flood | Slowloris |
|-----|-------------|---------------------|-----------|
| 공격 방식 | SYN만 보내고 ACK 안 보냄 | 3-Way Handshake 완료 | 느린 HTTP 요청 |
| 서버 상태 | Half-open 연결 누적 | Full Connection 누적 | 스레드/메모리 점유 |
| IP Spoofing | 필수 (가짜 IP 사용) | 불가능 (실제 IP 필요) | 불필요 |
| 주요 방어 | SYN Cookies | Rate Limiting, WAF, CDN | 타임아웃, Nginx |
| 공격 난이도 | 상대적으로 쉬움 | 봇넷 필요 (높음) | 단일 PC로 가능 (낮음) |

### QUIC/HTTP2/애플리케이션 레벨 공격

| 구분 | QUIC Initial Flood | HTTP/2 Rapid Reset | Bcrypt DoS |
|-----|-------------------|-------------------|------------|
| 공격 방식 | 가짜 IP로 Initial 패킷 폭탄 | 스트림 열고 즉시 취소 반복 | 로그인 요청 폭탄 |
| 고갈 자원 | CPU (암호화 연산) | CPU/메모리 (스트림 처리) | CPU (해시 연산) |
| IP Spoofing | 가능 | 불필요 | 불필요 |
| 주요 방어 | Retry Token | RST 비율 추적 | Rate Limiting, 입력값 제한 |
| 특징 | TLS 1.3 연산 악용 | 단일 연결로 수십만 회 공격 | 정상 HTTP 요청 형태 |
