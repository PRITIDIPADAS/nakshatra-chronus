function out = lvf_false_change(T, lam0, dlam, ice)
% Why SPHEREx cannot be blinked.
% A linear variable filter gives every pixel its own wavelength. A star that did not change
% still looks brighter or fainter when it lands on a pixel of another colour.
% T: stellar temperature (K). lam0: wavelength of visit 1 (micron). dlam: colour offsets (micron).
% ice: optional depth of a 3.05 micron water-ice band (0..1).
% Returns the apparent fractional change in flux for each offset.
  if nargin < 4, ice = 0; end
  f0 = star_flux(T, lam0, ice);
  f1 = star_flux(T, lam0 + dlam, ice);
  out.dlam = dlam;
  out.apparent_change = f1 ./ f0 - 1;
end

function f = star_flux(T, lam, ice)
  h = 6.62607015e-34; c = 2.99792458e8; kB = 1.380649e-23;
  L = lam * 1e-6;
  nu = c ./ L;
  f = (2 * h * nu.^3 / c^2) ./ (exp(h * nu ./ (kB * T)) - 1);   % F_nu shape
  f = f .* (1 - ice * exp(-0.5 * ((lam - 3.05) / 0.12).^2));
end
