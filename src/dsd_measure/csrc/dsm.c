/* Reference delta-sigma modulator core (public design: error feedback, 1 bit).
 *
 * Given the input u[n] (|u| < 1) and the noise-transfer-function coefficients b[], a[]
 * (monic, a[0] = b[0] = 1), computes v[n] = +/-1 with v = u + NTF * e, e = v - w.
 * Returns the number of samples at which |w| exceeded 'limit' (overload counter); *wmax is
 * raised to the largest |w| seen (in/out, so blocks can be chained).
 * State is in/out so long signals can be processed in blocks.
 */
#include <stddef.h>

int dsm_run(const double *u, signed char *v, size_t n, const double *b, const double *a,
            int order, double *ebuf, double *sbuf, double limit, double *wmax)
{
    /* ebuf: last 'order' errors (newest first). sbuf: last 'order' values of s = (NTF-1)*e. */
    int over = 0;
    double wm = *wmax;
    for (size_t i = 0; i < n; i++) {
        /* IIR part: s[n] = sum (b_k - a_k) e[n-k] - sum_{k>=1} a_k s[n-k] */
        double acc = 0.0;
        for (int k = 1; k <= order; k++)
            acc += (b[k] - a[k]) * ebuf[k - 1] - a[k] * sbuf[k - 1];
        double s = acc;
        double w = u[i] + s;
        double q = (w >= 0.0) ? 1.0 : -1.0;
        double e = q - w;
        if (w > limit || w < -limit) over++;
        if (w > wm) wm = w;
        if (-w > wm) wm = -w;
        for (int k = order - 1; k > 0; k--) {
            ebuf[k] = ebuf[k - 1];
            sbuf[k] = sbuf[k - 1];
        }
        ebuf[0] = e;
        sbuf[0] = s;
        v[i] = (signed char)q;
    }
    *wmax = wm;
    return over;
}
