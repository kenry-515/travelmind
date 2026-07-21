/**
 * TravelMind Agent — Device ID Manager
 *
 * Generates and persists a random UUID in localStorage as the anonymous
 * user identifier. Sent as X-Device-ID header on every API request.
 * No registration required — this is the sole identity for anonymous users.
 */

const DEVICE_ID_KEY = 'travelmind_device_id'

export function getDeviceId(): string {
  let id = localStorage.getItem(DEVICE_ID_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(DEVICE_ID_KEY, id)
  }
  return id
}
