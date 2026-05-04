#include <Adafruit_NeoPixel.h>

#define PIN 5          // Change if you're using a different GPIO
#define NUM_LEDS 12    // Your ring has 12 LEDs

Adafruit_NeoPixel ring(NUM_LEDS, PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  ring.begin();
  ring.setBrightness(50); // Keep low for safety
  ring.show();            // Initialize all off
}

void loop() {
  // 🔴 Turn all LEDs RED
  for (int i = 0; i < NUM_LEDS; i++) {
    ring.setPixelColor(i, ring.Color(255, 0, 0));
  }
  ring.show();
  delay(1000);

  // 🟢 Turn all LEDs GREEN
  for (int i = 0; i < NUM_LEDS; i++) {
    ring.setPixelColor(i, ring.Color(0, 255, 0));
  }
  ring.show();
  delay(1000);

  // 🔵 Turn all LEDs BLUE
  for (int i = 0; i < NUM_LEDS; i++) {
    ring.setPixelColor(i, ring.Color(0, 0, 255));
  }
  ring.show();
  delay(1000);
}
