function [score, fair, d] = fair_pair(det_a, det_b, lam_a, lam_b, bw_a, bw_b, rel_a, rel_b, zodi_a, zodi_b, nflag)
% Fair pair rule for two SPHEREx exposures. Mirrors backend/core.py pair_score.
% Same array, colours within half a channel width, same release, similar background.
  if det_a ~= det_b
    score = 0; fair = false; d = NaN; return
  end
  bw = 0.5 * (bw_a + bw_b);
  d = abs(lam_a - lam_b) / bw;
  score = 100 - 40 * min(1, d / 0.5) - 30 * nflag;
  if ~strcmp(rel_a, rel_b)
    score = score - 35;
  end
  if abs(zodi_a / max(zodi_b, 1e-9) - 1) > 0.2
    score = score - 15;
  end
  score = fix(max(score, 0));
  fair = score >= 70 && d <= 0.5;
end
