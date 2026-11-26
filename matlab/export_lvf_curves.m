function export_lvf_curves(outfile)
% Curves for the website: apparent change of a constant star versus the colour offset
% between two visits. Run: octave --eval "addpath('matlab'); export_lvf_curves('site/data/lvf_curves.json')"
  dl = linspace(-0.08, 0.08, 81);
  T = [3000 5800 10000];
  res.dlam_nm = dl * 1000;
  res.curves = struct('label', {}, 'change_percent', {});
  for i = 1:3
    r = lvf_false_change(T(i), 1.6, dl);
    res.curves(end + 1) = struct('label', sprintf('%d K star at 1.6 um', T(i)), 'change_percent', 100 * r.apparent_change);
  end
  r = lvf_false_change(3000, 3.05 - 0.06, dl, 0.4);
  res.curves(end + 1) = struct('label', '3000 K star on the edge of a 3.05 um ice band', 'change_percent', 100 * r.apparent_change);
  res.source = 'matlab/export_lvf_curves.m, run with GNU Octave';
  fid = fopen(outfile, 'w'); fputs(fid, jsonencode(res)); fclose(fid);
end
