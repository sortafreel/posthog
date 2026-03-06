import { EventType } from '@posthog/rrweb-types'
import type { eventWithTime } from '@posthog/rrweb-types'

import { selectNewEvents, shouldUpdatePlaybackPosition } from './snapshot-sync'

function evt(timestamp: number): eventWithTime {
    return { timestamp, type: EventType.IncrementalSnapshot, data: {} } as unknown as eventWithTime
}

describe('selectNewEvents', () => {
    it('finds events inserted before existing ones (out-of-order loading)', () => {
        const all = [evt(50), evt(100), evt(200)]
        const current = [evt(100), evt(200)]
        const result = selectNewEvents(all, current)
        expect(result.map((e) => e.timestamp)).toEqual([50])
    })

    it('finds events interspersed with existing ones', () => {
        const all = [evt(100), evt(150), evt(200), evt(250)]
        const current = [evt(100), evt(200)]
        const result = selectNewEvents(all, current)
        expect(result.map((e) => e.timestamp)).toEqual([150, 250])
    })

    it.each([
        {
            name: 'empty allSnapshots → empty result',
            all: [] as eventWithTime[],
            current: [evt(100)],
        },
        {
            name: 'empty currentEvents → returns all',
            all: [evt(100), evt(200)],
            current: [] as eventWithTime[],
        },
        {
            name: 'both empty → empty result',
            all: [] as eventWithTime[],
            current: [] as eventWithTime[],
        },
    ])('$name', ({ all, current }) => {
        const result = selectNewEvents(all, current)
        if (all.length === 0) {
            expect(result).toEqual([])
        } else if (current.length === 0) {
            expect(result.map((e) => e.timestamp)).toEqual(all.map((e) => e.timestamp))
        }
    })
})

describe('shouldUpdatePlaybackPosition', () => {
    it.each([
        {
            name: 'first call (no previous update) → true',
            newTimestamp: 10000,
            lastUpdate: undefined,
            expected: true,
        },
        {
            name: 'just after last update (< 5s) → false',
            newTimestamp: 10000,
            lastUpdate: 9000,
            expected: false,
        },
        {
            name: 'exactly 5s after last update → false (not strictly greater)',
            newTimestamp: 15000,
            lastUpdate: 10000,
            expected: false,
        },
        {
            name: '5.001s after last update → true',
            newTimestamp: 15001,
            lastUpdate: 10000,
            expected: true,
        },
        {
            name: 'well after last update (30s) → true',
            newTimestamp: 40000,
            lastUpdate: 10000,
            expected: true,
        },
    ])('$name', ({ newTimestamp, lastUpdate, expected }) => {
        expect(shouldUpdatePlaybackPosition(newTimestamp, lastUpdate)).toBe(expected)
    })
})
