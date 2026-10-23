# E32 V2 alpha.12 — preserve internal heap during HTTPS updates

The serial trace from the existing updater reports certificate verification
failure FFFFBD70 (-0x4290). The pinned mbedTLS implementation combines
RSA_PUBLIC_FAILED (-0x4280) with MPI_ALLOC_FAILED (-0x0010): this is an
allocation failure while verifying the signature, not evidence of an untrusted CA.
The pinned SDK allocates TLS memory exclusively from internal RAM.

Release discovery previously reserved a 32 KiB internal response string before
the TLS handshake. Bounded release/manifest response storage now explicitly uses
E32 PSRAM, with no internal fallback. The ordinary JSON string is created only
after the HTTPS client has been destroyed. Failed allocation and oversized
responses still stop the request. Certificate, hostname, redirect, manifest,
image checksum, flash readback and boot selection checks remain enabled.

This addresses a demonstrated internal-memory competitor. It does not yet
establish that all real-board update failures are fixed. A successful actual
HTTPS discovery and subsequent verified firmware update remain required.
Settings, filesystem, partition layout and physical-output restrictions are
unchanged. Use only the published app-only firmware.bin; never erase or upload
the factory image or SPIFFS for this update. Keep EMS disconnected.

# E32 V2 v0.1.0-e32v2-alpha.11 — testkandidaat

De updatecatalogus controleert alle maximaal twaalf releaseberichten voordat
hij de twee laatst gepubliceerde passende firmwareversies aanbiedt. De echte
GitHub-lijst plaatste alpha.10 na9,8en7; eerder stopte de controle al bij9en8.
Publicatietijd wordt alleen gebruikt als geldige UTC-datum. Per release blijven
de vaste hosts, passende manifesten en alle bestaande download-/image-/readback-
controles vereist. Een fout later in de scan levert geen gedeeltelijke toelating.
De meegeleverde HA-bron bevat de afzonderlijk uitgebrachte dev17-correctie.

De toelatingsdiagnostiek van alpha.10 blijft aanwezig; er is geen automatische
commandoherhaling of verruiming van grants, replaycontrole of fysieke uitgangen.
De eerdere22°C-afwijzing is nog niet verklaard. De alpha.10-HTTP-upload werd
verbroken; een echte readback bevestigde alpha.9 met ongewijzigde configuratie.
Die uitval is niet door deze cataloguscorrectie opgelost. Instellingenformaat,
partities, fysieke voorwaarden en open herstelacceptatie blijven behouden.

# E32 V2 alpha.10 — bounded command-admission diagnostics

Experimental bench-test candidate. The normal HA connection/configuration path
is live-verified, while a subsequent 22°C command was rejected. Its precise
admission reason has not yet been established; this release adds observations,
without changing admission rules or enabling heating.

- Rejected envelope acknowledgements include a static `rejection_reason` from
  the existing admission decision. No grant token, private setting or secret hash
  is added to diagnostics.
- The existing authenticated state snapshot optionally includes the most recent
  user-command admission: binding, sequence, received revision/time and outcome.
  This bounded RAM record clears when the session/owner is invalidated. It is
  neither an execution receipt nor a measurement timestamp or durable state.
- Expired grants, changed duplicates and other rejected commands still cannot
  execute. Diagnostics never retry a command, refresh a grant or change a
  watermark. Qualified measurements, hydraulic commissioning and physical output
  rights remain separate and unchanged.
- Settings/update schemas and partitions are unchanged. Current HA16 sources
  accompany this firmware source commit; no HA installation is performed by OTA.

Use the immutable CI app-only release with current configuration/source/plan
before-and-after checks. Cold/power-loss/USB recovery and physical acceptance
remain open. The earlier live command failure is not declared fixed by adding
its diagnostic field.

# E32 V2 alpha.9 — conditional device settings for Home Assistant linking

Experimental bench-test candidate. Physical boiler/TRV/GPIO authority is unchanged.

- Authenticated device-settings reads return an opaque random ETag associated
  with this boot, browser session and the complete saved settings. The private
  settings digest stays on the controller; broker/weather secret hashes are not
  exposed as ETags.
- A settings POST with `If-Match` is rejected with HTTP412 before merging or
  saving if another edit changed the settings or the session/readback expired.
  Unquoted, weak, wildcard, combined and other-session tags are rejected. Existing
  local forms remain compatible; cookie, origin, CSRF and update guards remain.
- This is the firmware prerequisite for the normal Home Assistant connection
  step under development. It does not itself install that integration flow,
  select a room profile, validate measurements or enable heating.

Use the immutable CI release assets, app-only with private before/after snapshots.
Cold/power-loss/USB recovery and physical room/boiler acceptance remain separate.

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
