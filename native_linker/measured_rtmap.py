"""DUMP-CALIBRATED runtime map for the pass-3 pointer bake (skate boot fix).

The loader-sim's console runtime model is off by an un-derivable ~1.2 MB
(gfx/structural band). A full-memory dump of a boot gives the loader's REAL
per-asset block-5 layout (measured, `_skate_realmap.pkl`). The layout does NOT
depend on our alias values (only on FOLLOW pointers + the loader's allocator),
so baking pointers against the measured layout is correct.

rt(dom): dom = emitted-body block-5 offset (= disk_offset - assets_end, the
co_cursor domain the omap uses). Returns the measured runtime block-5 offset:
real_start(asset) + (dom - asset_body_offset). Assets we couldn't measure
(no unique needle / relocated) fall back to sim + interpolated divergence.
"""
import bisect, pickle


class MeasuredRuntimeMap:
    def __init__(self, simmap_pkl='_skate_simmap.pkl', realmap_pkl='_skate_realmap.pkl'):
        S = pickle.load(open(simmap_pkl, 'rb'))
        R = pickle.load(open(realmap_pkl, 'rb'))
        self.ae = S['assets_end']
        real = R['real']                     # stream_b5(asset start) -> real rt b5
        # per-asset: (body_off_lo, body_off_hi, real_start or None)
        self.spans = []
        for (i, nm, root, s, e) in S['spans']:
            lo = s - self.ae; hi = e - self.ae   # co_cursor domain
            rs = real.get(s - 64)                # measured real runtime start
            self.spans.append((lo, hi, rs))
        self.spans.sort()
        self._lo = [t[0] for t in self.spans]
        # divergence anchors (measured spans only) for interpolating misses:
        # divergence(body_off) = real_start - sim_rt(body_off_start)
        self.sim = None                      # set by assemble_zone (RuntimeMap)
        self._div = None
        self._meas = None; self._meas_lo = None
        self.stats = dict(measured=0, interp=0, simfallback=0)
        # max runtime END across measured assets — the header's block-5 size
        # MUST cover this, else late pointers land out-of-block and the loader
        # resolves them to null (the accessed=0 host-null crash).
        self.max_rt = max((rs + (hi - lo) for (lo, hi, rs) in self.spans
                           if rs is not None), default=0)

    def _build_div(self):
        # divergence table keyed by body_off_lo, from measured spans
        xs, ys = [], []
        for (lo, hi, rs) in self.spans:
            if rs is not None and self.sim is not None:
                xs.append(lo); ys.append(rs - self.sim.rt(lo))
        self._div = (xs, ys)

    def _interp_div(self, dom):
        if self._div is None:
            self._build_div()
        xs, ys = self._div
        if not xs:
            return 0
        j = bisect.bisect_right(xs, dom) - 1
        if j < 0:
            return ys[0]
        if j >= len(xs) - 1:
            return ys[-1]
        # linear interpolation between measured neighbors
        x0, x1 = xs[j], xs[j + 1]; y0, y1 = ys[j], ys[j + 1]
        return y0 + (y1 - y0) * (dom - x0) / (x1 - x0) if x1 > x0 else y0

    def rt(self, dom):
        # carry-forward from the nearest MEASURED anchor at/before dom: exact
        # inside a measured asset, near-exact for a following unmeasured one
        # (divergence is constant until the next inter-asset gap; with 83%
        # coverage those gaps are tiny). Purely measured — no sim, no drift.
        if self._meas_lo is None:
            self._meas = sorted((lo, rs) for (lo, hi, rs) in self.spans
                                if rs is not None)
            self._meas_lo = [t[0] for t in self._meas]
        j = bisect.bisect_right(self._meas_lo, dom) - 1
        if j >= 0:
            mlo, mrs = self._meas[j]
            # is dom inside this measured asset's own span? (exact vs carry)
            i = bisect.bisect_right(self._lo, dom) - 1
            if i >= 0 and self.spans[i][0] == mlo and self.spans[i][2] is not None:
                self.stats['measured'] += 1
            else:
                self.stats['interp'] += 1
            return mrs + (dom - mlo)
        self.stats['simfallback'] += 1
        return self.sim.rt(dom) if self.sim else dom
