import { RecordingSegment } from '~/types'

import { SnapshotStore } from '../snapshot-store/SnapshotStore'

export function convertSegmentKinds(
    segments: RecordingSegment[],
    snapshotStore: SnapshotStore,
    isLoadingSnapshots: boolean
): RecordingSegment[] {
    return segments.map((segment) => {
        if (snapshotStore.sourceCount > 0) {
            const startIdx = snapshotStore.getSourceIndexForTimestamp(segment.startTimestamp)
            const endIdx = snapshotStore.getSourceIndexForTimestamp(segment.endTimestamp)
            const hasUnloaded = snapshotStore.getUnloadedIndicesInRange(startIdx, endIdx).length > 0

            if (segment.kind === 'buffer' && !hasUnloaded) {
                return { ...segment, kind: 'gap' as const }
            }

            if (segment.kind === 'gap' && hasUnloaded) {
                return { ...segment, kind: 'buffer' as const, isLoading: isLoadingSnapshots }
            }
        }

        if (segment.kind === 'buffer') {
            return {
                ...segment,
                isLoading: isLoadingSnapshots,
            }
        }
        return segment
    })
}
