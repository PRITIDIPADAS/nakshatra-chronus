function [lo, hi] = wilson(h, n, z)
% Wilson score interval for h successes in n trials.
  if nargin < 3, z = 1.96; end
  p = h / n; d = 1 + z^2 / n;
  c = (p + z^2 / (2 * n)) / d;
  w = z * sqrt(p * (1 - p) / n + z^2 / (4 * n^2)) / d;
  lo = c - w; hi = c + w;
end
