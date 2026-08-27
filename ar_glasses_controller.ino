#include <Wire.h>
#include <U8g2lib.h>
#include <SoftwareSerial.h>

// SSD1306 128x32 OLED
U8G2_SSD1306_128X32_UNIVISION_F_HW_I2C oled(
  U8G2_R0,
  U8X8_PIN_NONE
);

// HC-05 主模块
// HC-05 TX -> Nano D10
// Nano D11 -> HC-05 RX，建议经过分压
const uint8_t HC05_RX = 10;
const uint8_t HC05_TX = 11;
SoftwareSerial hc05(HC05_RX, HC05_TX);

const char* BED_ID = "BED5";

struct Option {
  const char* id;
  const char* label;
};

const Option needs[] = {
  {"THIRSTY",  "THIRST"},
  {"ITCHY",    "ITCHY"},
  {"PAIN",     "PAIN"},
  {"POSITION", "POSITION"},
  {"ANXIETY",  "ANXIOUS"},
  {"MORE",     "MORE"}
};

const Option responses[] = {
  {"SMILE",  "SMILE"},
  {"THUMBS", "THUMBS"},
  {"HEART",  "HEART"},
  {"CLAP",   "CLAP"},
  {"SAD",    "SAD"},
  {"MORE",   "MORE"}
};

enum Screen {
  CARE_MENU,
  CARE_STATUS,
  FAMILY_MESSAGE,
  FAMILY_RESPONSE,
  FAMILY_STATUS
};

Screen screen = CARE_MENU;

uint8_t selectedNeed = 0;
uint8_t selectedResponse = 0;

String currentNeed = "NONE";
String currentResponse = "NONE";
String familyMessage = "You are doing great.";
String careStatus = "READY";
String familyStatus = "READY";

String usbBuffer;
String bluetoothBuffer;


// ---------- 通信 ----------

void sendEvent(const String& message) {
  // 发送给连接电脑的 USB/FTDI 串口
  Serial.println(message);
}

void processBluetooth(String line) {
  line.trim();

  if (line.length() == 0) return;

  // EEG 数据由 HC-05 从 EEG 模块接收后转发给电脑
  sendEvent("EEG_EVENT|" + line);

  // 可选：EEG 模块发出 ALERT 时，在 OLED 上提示
  String upper = line;
  upper.toUpperCase();

  if (upper == "ALERT" || upper == "EEG:ALERT") {
    careStatus = "CHECK PATIENT";
    screen = CARE_STATUS;
    render();
  }
}

void processCommand(String line) {
  line.trim();

  if (line.length() == 0) return;

  String upper = line;
  upper.toUpperCase();

  // 切换到护理需求界面
  if (upper == "MODE:CARE") {
    screen = CARE_MENU;
    careStatus = "READY";
    render();
    return;
  }

  // 切换到家人消息界面
  if (upper == "MODE:FAMILY") {
    screen = FAMILY_MESSAGE;
    familyStatus = "NEW MESSAGE";
    render();
    return;
  }

  // 切换到患者回应界面
  if (upper == "MODE:FAMILY_RESP") {
    screen = FAMILY_RESPONSE;
    render();
    return;
  }

  // 眼动系统发送当前光标位置
  if (upper.startsWith("NAV:")) {
    int index = upper.substring(4).toInt();

    if (screen == CARE_MENU && index >= 0 && index < 6) {
      selectedNeed = index;
      render();
    }

    if (screen == FAMILY_RESPONSE && index >= 0 && index < 6) {
      selectedResponse = index;
      render();
    }

    return;
  }

  // 眼动系统确认护理需求
  if (upper.startsWith("SELECT:")) {
    String id = upper.substring(7);
    id.trim();

    for (uint8_t i = 0; i < 6; i++) {
      if (id == needs[i].id) {
        selectedNeed = i;
        selectNeed();
        return;
      }
    }

    // 没有指定名称时，选择当前光标
    if (id.length() == 0) {
      selectNeed();
    }

    return;
  }

  // 眼动系统确认回应
  if (upper.startsWith("SELECT_RESP:")) {
    String id = upper.substring(12);
    id.trim();

    for (uint8_t i = 0; i < 6; i++) {
      if (id == responses[i].id) {
        selectedResponse = i;
        selectResponse();
        return;
      }
    }

    return;
  }

  // 电脑或护理端发送家人消息
  if (upper.startsWith("FAMILY_MSG:")) {
    // 保留原始大小写，方便显示英文消息
    familyMessage = line.substring(11);
    familyMessage.trim();

    screen = FAMILY_MESSAGE;
    familyStatus = "NEW MESSAGE";
    render();
    return;
  }

  // 护理人员确认已收到请求
  if (upper == "CAREGIVER:ACK") {
    careStatus = "CAREGIVER ACK";
    screen = CARE_STATUS;

    sendEvent(
      "CARE_ACK|bed=" + String(BED_ID) +
      "|need=" + currentNeed
    );

    render();
    return;
  }

  // 护理完成
  if (upper == "CAREGIVER:DONE") {
    careStatus = "REQUEST DONE";
    screen = CARE_STATUS;

    sendEvent(
      "CARE_COMPLETE|bed=" + String(BED_ID) +
      "|need=" + currentNeed
    );

    render();
    return;
  }
}

void readSerialLine(Stream& stream, String& buffer, bool isBluetooth) {
  while (stream.available()) {
    char c = stream.read();

    if (c == '\n' || c == '\r') {
      if (buffer.length() > 0) {
        if (isBluetooth) {
          processBluetooth(buffer);
        } else {
          processCommand(buffer);
        }

        buffer = "";
      }
    } else {
      buffer += c;

      // 防止异常数据造成 String 无限增长
      if (buffer.length() > 100) {
        buffer = "";
      }
    }
  }
}


// ---------- 功能 ----------

void selectNeed() {
  currentNeed = needs[selectedNeed].id;
  careStatus = "REQUEST SENT";
  screen = CARE_STATUS;

  sendEvent(
    "CARE_REQUEST|bed=" + String(BED_ID) +
    "|need=" + currentNeed
  );

  render();
}

void selectResponse() {
  currentResponse = responses[selectedResponse].id;
  familyStatus = "RESPONSE SENT";
  screen = FAMILY_STATUS;

  sendEvent(
    "FAMILY_RESPONSE|response=" + currentResponse
  );

  render();
}


// ---------- OLED 界面 ----------

void drawHeader(const char* title) {
  oled.setFont(u8g2_font_5x8_tf);
  oled.drawStr(0, 8, title);
  oled.drawHLine(0, 10, 128);
}

void drawOptionGrid(
  const char* title,
  const Option* options,
  uint8_t selected
) {
  oled.clearBuffer();
  drawHeader(title);

  for (uint8_t i = 0; i < 6; i++) {
    uint8_t column = i % 3;
    uint8_t row = i / 3;

    uint8_t x = column * 42;
    uint8_t y = 20 + row * 11;

    if (i == selected) {
      oled.drawBox(x, y - 8, 41, 10);
      oled.setDrawColor(0);
    }

    oled.drawStr(x + 2, y, options[i].label);

    oled.setDrawColor(1);
  }

  oled.sendBuffer();
}

void drawCareMenu() {
  drawOptionGrid("CARE NEEDS / BED 5", needs, selectedNeed);
}

void drawResponseMenu() {
  drawOptionGrid("CHOOSE RESPONSE", responses, selectedResponse);
}

void drawCareStatus() {
  oled.clearBuffer();
  drawHeader("CARE REQUEST");

  oled.setFont(u8g2_font_5x8_tf);

  String line1 = currentNeed;
  String line2 = careStatus;

  oled.drawStr(0, 19, line1.c_str());
  oled.drawStr(0, 30, line2.c_str());

  oled.sendBuffer();
}

void drawFamilyMessage() {
  oled.clearBuffer();
  drawHeader("FROM FAMILY");

  oled.setFont(u8g2_font_5x8_tf);

  String msg = familyMessage;

  if (msg.length() > 21) {
    msg = msg.substring(0, 21);
  }

  oled.drawStr(0, 20, msg.c_str());
  oled.drawStr(0, 30, "MODE:FAMILY_RESP");

  oled.sendBuffer();
}

void drawFamilyStatus() {
  oled.clearBuffer();
  drawHeader("FAMILY");

  oled.setFont(u8g2_font_5x8_tf);

  oled.drawStr(0, 19, currentResponse.c_str());
  oled.drawStr(0, 30, familyStatus.c_str());

  oled.sendBuffer();
}

void render() {
  switch (screen) {
    case CARE_MENU:
      drawCareMenu();
      break;

    case CARE_STATUS:
      drawCareStatus();
      break;

    case FAMILY_MESSAGE:
      drawFamilyMessage();
      break;

    case FAMILY_RESPONSE:
      drawResponseMenu();
      break;

    case FAMILY_STATUS:
      drawFamilyStatus();
      break;
  }
}


// ---------- Arduino ----------

void setup() {
  Serial.begin(115200);
  hc05.begin(9600);

  oled.begin();
  oled.setContrast(255);

  render();

  Serial.println("READY|OLED=SSD1306|ADDR=0x3C|BED=5");
}

void loop() {
  readSerialLine(Serial, usbBuffer, false);
  readSerialLine(hc05, bluetoothBuffer, true);
}
