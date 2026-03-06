import { eventWithTime } from '@posthog/rrweb-types'

import { findNewEvents } from '../sessionRecordingPlayerLogic'

/**
 * Determines which new events to add to the rrweb replayer.
 *
 * Sources may load out of order (e.g. seek to minute 30, then load minute 5).
 * New events can appear before, between, or after existing events.
 * Uses timestamp-count matching to find the diff.
 */
export function selectNewEvents(allSnapshots: eventWithTime[], currentEvents: eventWithTime[]): eventWithTime[] {
    return findNewEvents(allSnapshots, currentEvents)
}

const POSITION_UPDATE_INTERVAL_MS = 5000

/**
 * Determines whether the playback position should be reported to the
 * LoadingScheduler so it can slide its buffer window forward.
 */
export function shouldUpdatePlaybackPosition(newTimestamp: number, lastUpdateTimestamp: number | undefined): boolean {
    return !lastUpdateTimestamp || newTimestamp - lastUpdateTimestamp > POSITION_UPDATE_INTERVAL_MS
}
