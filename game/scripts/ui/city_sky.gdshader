// Himmel des Stadtpanoramas (It. 75).
//
// Im Vorbild (Heroes 4) ist der Himmel ein Drittel des Stadtbilds und
// traegt die Stimmung der Fraktion: blau mit Wolken bei den Menschen,
// gluehend rot-orange beim Totenreich. Verlauf von oben zum Horizont plus
// Wolkenfeld aus Rauschen, auf eine gedachte Wolkendecke projiziert, damit
// die Wolken zum Horizont hin flacher und dichter werden.
shader_type sky;

uniform vec3 top_col : source_color = vec3(0.30, 0.48, 0.76);
uniform vec3 horizon_col : source_color = vec3(0.80, 0.85, 0.88);
uniform vec3 cloud_col : source_color = vec3(0.96, 0.96, 0.95);
uniform vec3 cloud_shade : source_color = vec3(0.62, 0.66, 0.74);
uniform vec3 ground_col : source_color = vec3(0.30, 0.30, 0.26);
uniform float cover = 0.48;
uniform sampler2D noise : repeat_enable, filter_linear;

void sky() {
	vec3 d = EYEDIR;
	float up = clamp(d.y, 0.0, 1.0);
	vec3 col = mix(horizon_col, top_col, pow(up, 0.55));
	if (d.y > 0.0) {
		vec2 uv = d.xz / (d.y + 0.12) * 0.22;
		float n = texture(noise, uv).r * 0.65 + texture(noise, uv * 2.3 + vec2(0.4, 0.1)).r * 0.35;
		float c = smoothstep(cover, cover + 0.22, n);
		// Unterseite der Wolken dunkler, oben hell.
		float shade = smoothstep(cover, cover + 0.45, n);
		vec3 cc = mix(cloud_shade, cloud_col, shade);
		// Zum Horizont hin im Dunst verschwinden.
		c *= smoothstep(0.0, 0.18, d.y);
		col = mix(col, cc, c * 0.9);
	} else {
		col = mix(horizon_col, ground_col, smoothstep(0.0, 0.25, -d.y));
	}
	COLOR = col;
}
