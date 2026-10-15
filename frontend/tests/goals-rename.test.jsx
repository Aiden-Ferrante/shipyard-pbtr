/* GoalRail's unmount-commit must send the edit to the row it was typed on.
 *
 * The regression: the pending-rename ref was assigned during render, but the
 * cleanup that reads it runs *after* the render that switched rows — so editing
 * A's title and clicking B sent `PATCH /api/problems/B {title: A's edit}`,
 * silently renaming the newly selected problem. These tests pin the contract:
 * keystrokes belong to the row they were aimed at, wherever the commit fires.
 */
import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { GoalRail } from '../src/goals'

const mkRow = (id, title) => ({
  id, title, draft: false, pinned: false, active: false, standing: 'open',
  child_count: 0, repo: null, anchored: false,
})

const noop = () => {}
const rail = row => (
  <GoalRail embedded row={row} onChanged={noop} onError={noop} onOpenWindow={noop} />
)

// Every mount in the rail (argument, bearings) fetches; an empty object
// satisfies them all. Only the PATCH calls matter to these tests.
const patches = () =>
  fetch.mock.calls.filter(([, init]) => init?.method === 'PATCH')

beforeEach(() => {
  cleanup()
  vi.stubGlobal('fetch', vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({}) })))
})

describe('the pending rename', () => {
  it('follows the row it was typed on when the selection changes', () => {
    const a = mkRow('id-a', 'Alpha')
    const { rerender, getByLabelText } = render(rail(a))
    fireEvent.change(getByLabelText('rename Alpha'), { target: { value: 'Alpha, sharpened' } })

    rerender(rail(mkRow('id-b', 'Beta')))

    const sent = patches()
    expect(sent).toHaveLength(1)
    expect(sent[0][0]).toBe('/api/problems/id-a')
    expect(JSON.parse(sent[0][1].body)).toEqual({ title: 'Alpha, sharpened' })
  })

  it('commits on unmount — closing the drawer must not lose the edit', () => {
    const a = mkRow('id-a', 'Alpha')
    const { unmount, getByLabelText } = render(rail(a))
    fireEvent.change(getByLabelText('rename Alpha'), { target: { value: 'Alpha, kept' } })

    unmount()

    const sent = patches()
    expect(sent).toHaveLength(1)
    expect(sent[0][0]).toBe('/api/problems/id-a')
  })

  it('sends nothing when nothing was typed', () => {
    const { rerender, unmount } = render(rail(mkRow('id-a', 'Alpha')))
    rerender(rail(mkRow('id-b', 'Beta')))
    unmount()
    expect(patches()).toHaveLength(0)
  })

  it('does not double-send an edit already committed by blur', () => {
    const a = mkRow('id-a', 'Alpha')
    const { rerender, getByLabelText } = render(rail(a))
    const input = getByLabelText('rename Alpha')
    fireEvent.change(input, { target: { value: 'Alpha, blurred' } })
    fireEvent.blur(input)
    const afterBlur = patches().length
    expect(afterBlur).toBe(1)

    rerender(rail(mkRow('id-b', 'Beta')))
    expect(patches()).toHaveLength(afterBlur)
  })

  it('an escaped edit is abandoned, not committed', () => {
    const a = mkRow('id-a', 'Alpha')
    const { unmount, getByLabelText } = render(rail(a))
    const input = getByLabelText('rename Alpha')
    fireEvent.change(input, { target: { value: 'Alpha, discarded' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    unmount()
    expect(patches()).toHaveLength(0)
  })
})
