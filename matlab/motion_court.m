function out = motion_court(t, X, Y, eX, eY, fx, fy)
% Motion court: fixed (H0), linear motion (H1), motion plus parallax (H2).
% t in years, X and Y in arcsec. Lowest BIC wins. Mirrors backend/core.py motion_fit.
  t = t(:); X = X(:); Y = Y(:); n = numel(t);
  w = [1 ./ eX(:).^2; 1 ./ eY(:).^2];
  y = [X; Y];
  tc = t - mean(t); O = ones(n, 1); Z = zeros(n, 1);
  cols = {[O; Z], [Z; O], [tc; Z], [Z; tc], [fx(:); fy(:)]};
  names = {'H0', 'H1', 'H2'}; ks = [2 4 5];
  use = true(1, 3);
  if n < 6 || (max(t) - min(t)) < 0.25
    use(3) = false;
  end
  sw = sqrt(w);
  chi = inf(1, 3); P = cell(1, 3); C = cell(1, 3);
  for i = find(use)
    A = cell2mat(cols(1:ks(i)));
    Aw = A .* sw;
    p = Aw \ (y .* sw);
    chi(i) = sum(w .* (y - A * p).^2);
    P{i} = p; C{i} = pinv(Aw' * Aw);
  end
  dof = 2 * n - ks;
  s2 = max(1, min(chi(use) ./ max(dof(use), 1)));
  bic = chi / s2 + ks * log(2 * n);
  [~, j] = min(bic(2:3)); j = j + 1;
  if ~use(j), j = 2; end
  p = P{j}; cv = C{j} * s2;
  out.model = names{j};
  out.dbic = bic(1) - bic(j);
  out.pm_ra = p(3); out.pm_dec = p(4);
  out.pm = hypot(p(3), p(4));
  out.e_ra = sqrt(cv(3, 3)); out.e_dec = sqrt(cv(4, 4));
  out.reduced_chi2 = s2;
  if out.dbic > 10
    out.verdict = 'Motion model preferred';
  elseif out.dbic < -2
    out.verdict = 'Fixed position preferred';
  else
    out.verdict = 'Inconclusive';
  end
end
