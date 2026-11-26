function run_crosscheck(infile, outfile)
% Read cases written by tests/test_matlab_crosscheck.py, compute with the MATLAB
% re-implementation, write the answers as JSON.
  cases = jsondecode(fileread(infile));
  res = struct();
  m = cases.motion;
  for i = 1:numel(m)
    c = m(i);
    r = motion_court(c.t, c.X, c.Y, c.eX, c.eY, c.fx, c.fy);
    res.motion(i) = struct('model', r.model, 'dbic', r.dbic, 'pm', r.pm, 'verdict', r.verdict);
  end
  p = cases.pairs;
  for i = 1:numel(p)
    c = p(i);
    [s, f, d] = fair_pair(c.det_a, c.det_b, c.lam_a, c.lam_b, c.bw_a, c.bw_b, c.rel_a, c.rel_b, c.zodi_a, c.zodi_b, c.nflag);
    res.pairs(i) = struct('score', s, 'fair', f);
  end
  z = cases.z;
  res.z = diff_z(z.i1, z.i2, z.v1, z.v2, z.k, z.f, z.s);
  w = cases.wilson;
  for i = 1:size(w, 1)
    [lo, hi] = wilson(w(i, 1), w(i, 2));
    res.wilson(i, :) = [lo hi];
  end
  fid = fopen(outfile, 'w'); fputs(fid, jsonencode(res)); fclose(fid);
end
