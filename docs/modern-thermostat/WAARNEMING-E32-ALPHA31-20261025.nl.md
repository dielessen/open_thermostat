# E32 alpha31 — verse waarneming, geen installatieclaim

Alleen-lezen voorcontrole, 25 oktober 2026 om 01:50:09 UTC. **HA dev44 en E32
alpha31 worden nu waargenomen.** De eerdere nacontrole van 00:32:01 UTC zag nog
alpha28; die oudere uitkomst blijft als historische momentopname bewaard.

| Gegeven | Verse waarneming |
| --- | --- |
| HA | dev44/Core 2026.10.3, bron `659879e`, entry geladen en shadow_ready |
| E32 | `v0.1.0-e32v2-alpha.31`, bron `659879e52b3e0e517e8dea1e28edb2d189c38c77` |
| ELF-descriptor | `045dfe53a69c1a6f084e868eddfd15e9b1e6e94408e6a323935d58ab96804b84` |
| Web | `6ec3c7d46b254dcadf9193c618ce08483c98b8c2d3a771063ab88b8a598ffdac` |
| Boot/update | Uptime 3133s, reset_reason3, app/boot-slot0; idle, geen boot_pending/herstart gepland |
| Configuratie | SOURCE5 en dezelfde configuratie-/profiel-digests; geen automatische bronkwalificatie |
| Uitvoer | Ketel/kraan/forwarding uit; EMS-TX/polls/testframes nul; passieve ontvangst actueel |

De versie/bron/ELF/web komen overeen met de eerder gepubliceerde alpha31.
De uitvoerder, methode en exacte gebeurtenis waardoor die installatie tot stand
kwam zijn niet vastgesteld. Een lagere uptime en een andere resetreden bewijzen
geen bootcontinuïteit met de eerdere alpha28-waarneming. Deze releaseopdracht
heeft geen E32-upload, reboot, rollback of native HTTPS-proef gestart.

De voorcontrole stopte terecht op de veranderde identiteit. De actuele basis
wordt opnieuw beoordeeld voor uitsluitend een latere HA-componentupdate;
alpha28 wordt niet teruggezet. De oorspronkelijke uploader-watchdogoorzaak en
fysieke herstelroute zijn hiermee niet verklaard. Alpha31 waarnemen verleent
geen toestemming of bewijs om een volgende flashpoging te herhalen.

Bewijs: `out/combined-dev45-alpha32-20261025/SAFE-PREFLIGHT-initial-alpha31-drift.json`.
Tado blijft de actieve regelaar; actieve bèta- en fysieke acceptatie blijven open.

**English:** Fresh readonly evidence reports HA44/E32alpha31, matching the earlier
public source/ELF/web identities. This task did not upload firmware; actor and
method are unknown. The prior alpha28 observation is historical. Current-baseline
review, original updater-cause recovery and physical qualification remain separate.
