function z = diff_z(i1, i2, v1, v2, k, f, s)
% Significance of a change between two fair co-adds:
% Z = (I2 - k I1) / sqrt(var2 + k^2 var1 + (f s)^2)
% f is the resampling error fraction measured on catalogue stars, s the local signal scale.
  z = (i2 - k .* i1) ./ sqrt(v2 + k.^2 .* v1 + (f .* s).^2);
end
