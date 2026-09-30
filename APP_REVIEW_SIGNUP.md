# App Review registration and cash purchases

App Review can sign into the existing student/instructor demo accounts without SMS,
or test registration using the synthetic numbers configured on the production server.
`APP_REVIEW_SIGNUP_PHONES` is a comma-separated explicit allowlist and
`APP_REVIEW_SIGNUP_CODE` is a six-digit fixed code. Both are disabled by default.
Provide the configured numbers and code privately in App Store Connect Review Notes.

The reviewer taps the usual send-code button and enters the provided code within
three minutes; resending creates a fresh verification request using the same code.
The fixture skips SMS delivery only for these numbers. It does not apply to password
reset or phone change, and fails closed for any number tied to a production wallet.
Accounts registered with these fixtures are assigned SANDBOX wallets on the server;
clients cannot choose the IAP environment. Never configure a real customer number.

Coupon redemption is permanently retired at `/cash/coupons/redeem/` with HTTP 410.
Old clients cannot redeem even previously valid coupons. Existing ledger records
and balances remain intact. The app and web UI have no coupon redemption controls.
On iOS, additional cash is acquired through verified Apple In-App Purchase.
