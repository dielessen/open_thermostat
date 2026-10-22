#pragma once
inline int stoppedScans=0;
inline int esp_wifi_scan_stop(){++stoppedScans;return 0;}
