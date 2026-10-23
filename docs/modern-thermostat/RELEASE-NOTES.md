# E32 V2 alpha.8 — bounded OTA upload headers and updater stack

Experimental bench-test candidate. Keep EMS disconnected; physical outputs remain
blocked until the existing commissioning checks pass.

- Authenticated multipart app/filesystem uploads no longer append three security
  headers for every chunk. The final response emits them once; cookie, origin,
  CSRF and updater-busy checks still run for each chunk and the final route.
- Flash SHA readback uses a separate non-inlined 1 KiB scratch frame, keeping its
  buffer out of the updater's TLS/download frame. Exact image length, board marker,
  streamed SHA, native validation, whole-image flash SHA and boot selection remain
  required. This bounds stack use; it does not establish the cause of the earlier
  alpha.6 manifest-stage reset.
- Alpha.7 was installed app-only on the development E32 and its published
  source/UI/ELF identities, confirmed boot and saved settings/program were verified.
  Its GitHub install attempt had reset to idle; local upload installed it but
  exposed the duplicate headers. These observations are not acceptance of alpha.8
  or proof of cold recovery, physical TRV operation or boiler heating.

Publish only through the existing full CI/release pipeline. Upload only the exact
published `firmware.bin`; preserve filesystem/settings and the previous valid slot.

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
- The complete release kit supplies pinned vendor source/notice archives,
  exact application source and objects, an offline relink recipe, and evidence
  that both original and deliberately modified Arduino libraries link. Required
  CI independently reproduces all 629 reviewed open SDK/runtime compilation
  units. The vendor binary-only archives retain their original provenance and
  notices; this is a target-specific distribution check.

## Candidate and update status

Release downloads are produced from the same clean source commit as their
firmware and embedded UI identity. Publication requires the current source,
relink and SDK reproduction evidence and all build/package checks. Source-only
`sources-e32v2-…` releases are not firmware updates. These notes do not claim
physical installation or acceptance.

After a verified firmware release is published, use the existing device updater
or upload only its `firmware.bin`. The web interface is embedded in the app.
**Do not erase flash, install the factory image or upload SPIFFS for this update.**
Preserve a private settings backup and the previous immutable alpha.6 release.
Verify firmware/source/UI identity, settings, network health and recovery after
installation. Software and simulated-browser checks do not prove physical
update/recovery behavior or qualify the bathroom sensor/TRV control chain.
