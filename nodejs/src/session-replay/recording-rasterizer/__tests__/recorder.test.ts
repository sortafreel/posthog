import { scaleDimensionsIfNeeded, setupUrlForPlaybackSpeed } from '../recorder'

describe('recorder', () => {
    describe('scaleDimensionsIfNeeded', () => {
        it.each([
            { width: 800, height: 600, expected: { width: 800, height: 600 }, desc: 'no scaling needed' },
            { width: 1920, height: 1080, expected: { width: 1920, height: 1080 }, desc: 'exactly at max' },
            {
                width: 3840,
                height: 2160,
                expected: { width: 1920, height: 1080 },
                desc: 'landscape scaled down',
            },
            {
                width: 1080,
                height: 3840,
                expected: { width: 540, height: 1920 },
                desc: 'portrait scaled down',
            },
            {
                width: 2560,
                height: 2560,
                expected: { width: 1920, height: 1920 },
                desc: 'square scaled down (height path)',
            },
            {
                width: 4000,
                height: 1000,
                expected: { width: 1920, height: 480 },
                desc: 'ultrawide scaled down',
            },
        ])('$desc (${width}x${height})', ({ width, height, expected }) => {
            expect(scaleDimensionsIfNeeded(width, height)).toEqual(expected)
        })

        it('respects custom maxSize', () => {
            expect(scaleDimensionsIfNeeded(2000, 1000, 1000)).toEqual({ width: 1000, height: 500 })
        })
    })

    describe('setupUrlForPlaybackSpeed', () => {
        it.each([
            {
                url: 'https://app.posthog.com/exporter?token=abc',
                speed: 8,
                expected: 'https://app.posthog.com/exporter?token=abc&playerSpeed=8',
            },
            {
                url: 'https://app.posthog.com/exporter?token=abc&playerSpeed=2',
                speed: 16,
                expected: 'https://app.posthog.com/exporter?token=abc&playerSpeed=16',
            },
        ])('sets playerSpeed=$speed on $url', ({ url, speed, expected }) => {
            expect(setupUrlForPlaybackSpeed(url, speed)).toBe(expected)
        })
    })
})
