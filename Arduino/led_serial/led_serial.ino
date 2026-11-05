// Jetson에서 시리얼로 받은 명령으로 LED를 켜고 끈다.
// 명령: "ON\n", "OFF\n"  →  응답: "ACK ON", "ACK OFF"

const int LED_PIN = LED_BUILTIN;  // Uno/Nano 보드 내장 LED (13번 핀)

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.begin(9600);
  Serial.println("READY");
}

void loop() {
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
