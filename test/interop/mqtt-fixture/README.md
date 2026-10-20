# Disposable localhost MQTT test fixture

Only for the opt-in native packet test; never a production broker configuration.
The publicly known fixture password is `fixture-only`; users are `fw-test`,
`ha-test` and `outside-test`, scoped to `test_therm/v1/`.
Bind the container only to127.0.0.1 on a temporary port. Remove it after testing.
No real Home Assistant/device/broker credentials are used here.
