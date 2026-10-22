# E32 V2 alpha.7 — controller status and separate firmware release discovery

Experimental bench-test candidate. **Keep EMS disconnected; boiler, TRV and
GPIO outputs remain blocked. This candidate is not approved for heating.**

- Authenticated controller status distinguishes compiled graph/controller
  contracts and limits from the active configuration and physical permissions.
  A compiled capability does not enable runtime control or certify a device.
- The managed web interface presents controller status without requiring a
  restart for ordinary display refreshes. The complete heating dashboard and
  end-to-end HA→E32→acknowledgement/TRV acceptance remain follow-up work.
- Firmware discovery searches up to twelve bounded GitHub release pages for
  at most two compatible E32 app releases. Home Assistant releases, drafts,
  missing firmware assets and incompatible manifests are skipped. A transport
  failure preserves the previous list. The image, board/layout, hash/readback
  and boot-selection checks are unchanged.
- Home Assistant integration packages have separate `ha-v…` releases. Installing
  an HA ZIP does not update this firmware or enable physical heating control.

## Candidate and update status

These notes describe the alpha.7 source candidate. Publication and installation
require completion of the target-specific source/notice/distribution review and
all existing build/package checks. The previously built clean candidate predates
this release-catalog change; a fresh build is required. No alpha.7 installation
is claimed by these notes.

After a verified firmware release is published, use the existing device updater
or upload only its `firmware.bin`. The web interface is embedded in the app.
**Do not erase flash, install the factory image or upload SPIFFS for this update.**
Preserve a private settings backup and the previous immutable alpha.6 release.
Verify firmware/source/UI identity, settings, network health and recovery after
installation. Software and simulated-browser checks do not prove physical
update/recovery behavior or qualify the bathroom sensor/TRV control chain.
