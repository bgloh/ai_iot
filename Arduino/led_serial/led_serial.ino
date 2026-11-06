// Jetson과 시리얼로 통신하며 LED(D7)를 제어하고 스위치(D6) 상태를 보고한다.
//
// Jetson → Arduino 명령:  "ON\n", "OFF\n"
// Arduino → Jetson 응답:  "ACK ON", "ACK OFF", "ERR <명령>"
// Arduino → Jetson 이벤트: "BTN PRESSED", "BTN RELEASED"

const int LED_PIN = 7;                // 디지털 7번 핀에 연결한 LED
const int BUTTON_PIN = 6;             // 디지털 6번 핀에 연결한 풀업 스위치 (누르면 LOW)
const unsigned long DEBOUNCE_MS = 30; // 스위치 떨림(채터링) 무시 시간

int lastReading = HIGH;               // 직전에 읽은 핀 값
int buttonState = HIGH;               // 디바운싱이 끝난 확정 상태
unsigned long lastChangeMs = 0;       // 핀 값이 마지막으로 바뀐 시각

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
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

void loop() {
  handleCommand();
  checkButton();
}
