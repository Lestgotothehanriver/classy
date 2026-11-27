import assert from "node:assert/strict";
import test from "node:test";

import { isPublicId, parseRoute, pathFor } from "../src/router.js";

const publicId = "2f6db65e-b12e-4dde-9b4b-9c274a172537";

function route(pathname, search = "") {
  return parseRoute({ pathname, search });
}

test("public detail paths retain opaque UUIDs", () => {
  assert.equal(pathFor(`lecture/${publicId}`), `/lectures/${publicId}`);
  assert.equal(pathFor(`teacher-profile/${publicId}`), `/instructors/${publicId}`);
  assert.equal(pathFor(`tutoring-post-detail/${publicId}`), `/tutoring-posts/${publicId}`);
  assert.equal(pathFor(`chat/${publicId}`), `/messages/${publicId}`);
  assert.equal(
    pathFor(`tutoring-registration/${publicId}/proof`),
    `/messages/${publicId}/registration/proof`,
  );
});

test("new browser paths parse into existing screen contracts", () => {
  assert.deepEqual(route(`/lectures/${publicId}`).params, { publicId });
  assert.deepEqual(route(`/instructors/${publicId}`).params, { publicId });
  assert.deepEqual(route(`/messages/${publicId}`).params, { roomPublicId: publicId });
  assert.deepEqual(route("/my/saved/lectures").page, "saved");
  assert.deepEqual(route("/my/saved/instructors").page, "saved-teachers");
  assert.deepEqual(route("/my/expired/lectures").page, "expired");
});

test("only UUIDv4-compatible opaque identifiers pass browser validation", () => {
  assert.equal(isPublicId(publicId), true);
  assert.equal(isPublicId("1"), false);
  assert.equal(isPublicId("not-a-uuid"), false);
});
