// Jetson과 시리얼로 통신하며 LED(D7)를 제어하고 스위치(D6) 상태를 보고한다.
// Part C~E 확장: 조도센서(A0) 값을 보고하고, 서보모터(D9)를 제어한다.
//
// Jetson → Arduino 명령:  "ON\n", "OFF\n"
//                         "LIGHT\n", "STREAM ON\n", "STREAM OFF\n", "SERVO <0~180>\n"   ← 추가
// Arduino → Jetson 응답:  "ACK ON", "ACK OFF", "ERR <명령>"
//                         "LIGHT <0~1023>", "ACK STREAM ON", "ACK STREAM OFF", "ACK SERVO <각도>"   ← 추가
// Arduino → Jetson 이벤트: "BTN PRESSED", "BTN RELEASED"
//                         STREAM ON 동안 0.1초마다 "LIGHT <0~1023>"   ← 추가

#include <Servo.h>                     // ← 추가

const int LED_PIN = 7;                // 디지털 7번 핀에 연결한 LED
const int BUTTON_PIN = 6;             // 디지털 6번 핀에 연결한 스위치 (외부 10kΩ 풀업, 누르면 LOW)
const unsigned long DEBOUNCE_MS = 30; // 스위치 떨림(채터링) 무시 시간

const int LIGHT_PIN = A0;             // ← 추가: 조도센서(CdS) 전압 분배 출력
const int SERVO_PIN = 9;              // ← 추가: 서보모터 신호선(주황)
const unsigned long STREAM_MS = 100;  // ← 추가: 조도 값 전송 주기 (0.1초)

int lastReading = HIGH;               // 직전에 읽은 핀 값
int buttonState = HIGH;               // 디바운싱이 끝난 확정 상태
unsigned long lastChangeMs = 0;       // 핀 값이 마지막으로 바뀐 시각

Servo servo;                          // ← 추가
bool streaming = false;               // ← 추가: true이면 조도 값을 계속 보낸다
unsigned long lastStreamMs = 0;       // ← 추가

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BUTTON_PIN, INPUT);         // 외부 10kΩ 풀업 사용 (외부 저항 없이 쓰려면 INPUT_PULLUP)
  servo.attach(SERVO_PIN);            // ← 추가
  servo.write(90);                    // ← 추가: 시작 위치는 가운데(90도)
  Serial.begin(9600);
  Serial.println("READY");
}

// Jetson이 보낸 명령을 처리한다.
void handleCommand() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "ON") {
      digitalWrite(LED_PIN, HIGH);
      Serial.println("ACK ON");
    } else if (cmd == "OFF") {
      digitalWrite(LED_PIN, LOW);
      Serial.println("ACK OFF");
    } else if (cmd == "LIGHT") {                 // ← 추가: 조도 값 한 번 읽기
      Serial.print("LIGHT ");
      Serial.println(analogRead(LIGHT_PIN));
    } else if (cmd == "STREAM ON") {             // ← 추가: 조도 값 계속 보내기
      streaming = true;
      Serial.println("ACK STREAM ON");
    } else if (cmd == "STREAM OFF") {            // ← 추가
      streaming = false;
      Serial.println("ACK STREAM OFF");
    } else if (cmd.startsWith("SERVO ")) {       // ← 추가: 서보 각도
      int deg = cmd.substring(6).toInt();
      if (deg >= 0 && deg <= 180) {
        servo.write(deg);
        Serial.print("ACK SERVO ");
        Serial.println(deg);
      } else {
        Serial.print("ERR ");
        Serial.println(cmd);
      }
    } else if (cmd.length() > 0) {
      Serial.print("ERR ");
      Serial.println(cmd);
    }
  }
}

// 스위치 상태가 바뀌면 Jetson에 알린다.
void checkButton() {
  int reading = digitalRead(BUTTON_PIN);

  if (reading != lastReading) {       // 값이 바뀌면 시간을 다시 잰다
    lastChangeMs = millis();
    lastReading = reading;
  }

  // 같은 값이 DEBOUNCE_MS 이상 유지되면 상태 변화로 확정한다.
  if (millis() - lastChangeMs > DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      Serial.println("BTN PRESSED");
    } else {
      Serial.println("BTN RELEASED");
    }
  }
}

// ← 추가: STREAM ON 상태이면 STREAM_MS마다 조도 값을 보낸다.
void streamLight() {
  if (streaming && millis() - lastStreamMs >= STREAM_MS) {
    lastStreamMs = millis();
    Serial.print("LIGHT ");
    Serial.println(analogRead(LIGHT_PIN));
  }
}

void loop() {
  handleCommand();
  checkButton();
  streamLight();                      // ← 추가
}
