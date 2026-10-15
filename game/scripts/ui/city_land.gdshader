// Gelaende des Stadtpanoramas (It. 75).
//
// Vorbild ist der Stadtschirm von Heroes 4: die Stadt steht auf einer
// Landschaft mit Terrassen, deren Kanten als Fels abbrechen, mit Wegen
// dazwischen und Bergen im Hintergrund. Gefaerbt wird hier nach drei
// Merkmalen, nicht nach UVs:
//
//   * NEIGUNG (Weltnormale): flach = Wiese, steil = Fels. Die Felskante
//     ist das, woran man die Terrassen erkennt.
//   * HOEHE: Felsbaender quer (Gesteinsschichten), auf den Bergen oben
//     heller und kahler.
//   * VERTEXFARBE rot = Weg. Die Wege legt CityView3D beim Bauen des
//     Gelaendes fest; ein zweites Wegenetz im Shader waere eine zweite
//     Wahrheit darueber, wo man laeuft.
//
// Palette je Fraktion setzt CityView3D (FACTION_LOOK). Die Struktur kommt
// aus denselben Strukturkarten wie der Schlachtfeldboden (Poly Haven, CC0,
// siehe assets/textures/battle/SOURCES.md).
shader_type spatial;
render_mode diffuse_burley;

uniform sampler2D detail_a : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_b : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_dirt : repeat_enable, filter_linear_mipmap;
uniform sampler2D noise : repeat_enable, filter_linear;
uniform float detail = 0.85;

uniform vec3 grass_dark : source_color = vec3(0.25, 0.34, 0.19);
uniform vec3 grass_mid : source_color = vec3(0.31, 0.42, 0.23);
uniform vec3 grass_light : source_color = vec3(0.34, 0.49, 0.23);
uniform vec3 grass_dry : source_color = vec3(0.45, 0.40, 0.25);
uniform vec3 rock_dark : source_color = vec3(0.30, 0.28, 0.25);
uniform vec3 rock_light : source_color = vec3(0.55, 0.52, 0.46);
uniform vec3 path_col : source_color = vec3(0.56, 0.48, 0.34);
uniform vec3 peak_col : source_color = vec3(0.62, 0.60, 0.58);
uniform float peak_from = 10.0;

varying vec3 wpos;
varying vec3 wnrm;
varying float path;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	path = COLOR.r;
}

void fragment() {
	vec2 p = wpos.xz;
	float sa = texture(detail_a, p * 0.33).r * 2.0;
	float sb = texture(detail_b, p * 0.21 + vec2(0.37, 0.11)).r * 2.0;
	float sd = texture(detail_dirt, p * 0.28).r * 2.0;
	float n1 = texture(noise, p * 0.055).r;
	float n2 = texture(noise, p * 0.15 + vec2(0.31, 0.77)).r;
	float n3 = texture(noise, p * 0.025 + vec2(0.53, 0.19)).r;

	// Wiese mit hellen und dunklen Partien (wie das Schlachtfeld).
	float t = smoothstep(0.20, 0.80, n1 * 0.65 + n3 * 0.35);
	vec3 grass = t < 0.5 ? mix(grass_dark, grass_mid, t * 2.0)
	                     : mix(grass_mid, grass_light, t * 2.0 - 1.0);
	grass = mix(grass, grass_dry, smoothstep(0.62, 0.80, n2) * 0.5);
	grass *= mix(1.0, mix(sa, sb, 0.5), detail);

	// Fels: auf steilen Flaechen SEITLICH abgetastet (x+z gegen y) - von
	// oben projiziert wurde die Struktur an der Wand zu Streifen gezogen
	// und die Kante sah verschmiert aus.
	vec2 ps = vec2(wpos.x + wpos.z * 0.7, wpos.y);
	float sr = texture(detail_dirt, ps * 0.45).r * 2.0;
	float nr = texture(noise, ps * 0.12).r;
	float strata = 0.78 + 0.22 * smoothstep(0.3, 0.7, sin(wpos.y * 9.0 + nr * 5.0) * 0.5 + 0.5);
	vec3 rock = mix(rock_dark, rock_light, smoothstep(0.25, 0.85, nr * 0.7 + n1 * 0.3));
	rock *= strata * mix(1.0, sr, detail);
	// Unten an der Kante dunkler: die Terrasse wirft dort ihren Schatten.
	float slope = 1.0 - clamp(wnrm.y, 0.0, 1.0);
	float r = smoothstep(0.18, 0.34, slope + (n2 - 0.5) * 0.10);

	vec3 col = mix(grass, rock, r);
	// Bergspitzen kahl und hell.
	col = mix(col, peak_col * mix(1.0, sd, detail),
		smoothstep(peak_from, peak_from + 2.5, wpos.y + (n1 - 0.5) * 2.0) * 0.85);
	// Wege: Erde mit weichem Rand, auf Fels nicht.
	float w = smoothstep(0.15, 0.65, path + (n2 - 0.5) * 0.25) * (1.0 - r);
	col = mix(col, path_col * mix(1.0, sd, detail), w);

	ALBEDO = col;
	ROUGHNESS = 0.95;
	SPECULAR = 0.2;
}
