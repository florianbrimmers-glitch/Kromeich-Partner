// Gelaende der Weltkarte im Stil der Heroes-4-Abenteuerkarte (It. 77).
//
// EIN durchgehendes Netz statt einer Platte je Kachel. Die Gelaendearten
// kommen als Gewichte in der Vertexfarbe (r Wald, g Sand, b Sumpf, a Berg;
// der Rest ist Wiese) und laufen dadurch weich ineinander - die harten
// Kachelkanten waren der Hauptgrund, warum die Karte wie ein Brettspiel
// aussah. Wasser ist die Tiefe: unter dem Wasserspiegel liegt Uferkies.
//
// NEBEL kommt aus einer kleinen Textur (eine Zelle je Kachel, linear
// gefiltert): 0 = unerforscht (Schleier), 0.5 = erkundet, 0.75 = sichtbar
// aber diesen Zug nicht erreichbar, 1 = erreichbar. Weil die Textur
// gefiltert wird, ist der Rand des Schleiers weich wie im Vorbild. Unter
// dem Schleier wird das Gelaende im Vertex-Shader FLACHGEDRUECKT - sonst
// verraeten die Berge, was man noch gar nicht gesehen hat.
shader_type spatial;
render_mode diffuse_burley;

uniform sampler2D detail_a : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_b : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_dirt : repeat_enable, filter_linear_mipmap;
uniform sampler2D noise : repeat_enable, filter_linear;
uniform sampler2D fog_tex : filter_linear;
uniform vec2 map_size = vec2(18.0, 26.0);
uniform float detail = 0.8;

uniform vec3 grass_dark : source_color = vec3(0.25, 0.34, 0.19);
uniform vec3 grass_mid : source_color = vec3(0.31, 0.42, 0.23);
uniform vec3 grass_light : source_color = vec3(0.36, 0.50, 0.24);
uniform vec3 grass_dry : source_color = vec3(0.45, 0.40, 0.25);
uniform vec3 forest_floor : source_color = vec3(0.17, 0.25, 0.12);
uniform vec3 sand_col : source_color = vec3(0.70, 0.60, 0.40);
uniform vec3 swamp_col : source_color = vec3(0.26, 0.30, 0.18);
uniform vec3 swamp_mud : source_color = vec3(0.22, 0.20, 0.14);
uniform vec3 rock_dark : source_color = vec3(0.30, 0.28, 0.25);
uniform vec3 rock_light : source_color = vec3(0.56, 0.52, 0.46);
uniform vec3 shore_col : source_color = vec3(0.55, 0.50, 0.38);
uniform vec3 shroud_dark : source_color = vec3(0.05, 0.06, 0.08);
uniform vec3 shroud_light : source_color = vec3(0.16, 0.17, 0.21);
uniform float water_level = -0.08;

varying vec3 wpos;
varying vec3 wnrm;
varying vec4 wgt;
varying float vis;

// Ausserhalb der Karte laeuft der Nebel ueber eine gute Kachel WEICH aus,
// statt hart abzubrechen - sonst endete die Karte mit einer geraden Kante.
float fog_at(vec2 xz) {
	vec2 uv = clamp((xz + vec2(0.5)) / map_size, vec2(0.0), vec2(1.0));
	vec2 o = max(-(xz + vec2(0.5)), xz + vec2(0.5) - map_size);
	float fade = 1.0 - smoothstep(0.0, 1.2, max(o.x, o.y));
	return textureLod(fog_tex, uv, 0.0).r * fade;
}

void vertex() {
	vec3 w = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vis = fog_at(w.xz);
	// Unter dem Schleier flach: kein Berg verraet sich.
	float seen = smoothstep(0.0, 0.25, vis);
	VERTEX.y = mix(0.02, VERTEX.y, seen);
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	wgt = COLOR;
}

void fragment() {
	vec2 p = wpos.xz;
	float sa = texture(detail_a, p * 0.55).r * 2.0;
	float sb = texture(detail_b, p * 0.37 + vec2(0.37, 0.11)).r * 2.0;
	float sd = texture(detail_dirt, p * 0.45).r * 2.0;
	float n1 = texture(noise, p * 0.09).r;
	float n2 = texture(noise, p * 0.23 + vec2(0.31, 0.77)).r;
	float n3 = texture(noise, p * 0.04 + vec2(0.53, 0.19)).r;

	float t = smoothstep(0.20, 0.80, n1 * 0.65 + n3 * 0.35);
	vec3 grass = t < 0.5 ? mix(grass_dark, grass_mid, t * 2.0)
	                     : mix(grass_mid, grass_light, t * 2.0 - 1.0);
	grass = mix(grass, grass_dry, smoothstep(0.64, 0.82, n2) * 0.45);
	grass *= mix(1.0, mix(sa, sb, 0.5), detail);

	vec3 forest = forest_floor * mix(1.0, sb, detail) * (0.85 + 0.3 * n2);
	vec3 sand = sand_col * mix(1.0, sd, detail * 0.8) * (0.92 + 0.16 * n1);
	vec3 swamp = mix(swamp_col, swamp_mud, smoothstep(0.45, 0.65, n2));
	swamp *= mix(1.0, sa, detail * 0.7);

	vec2 ps = vec2(wpos.x + wpos.z * 0.7, wpos.y);
	float sr = texture(detail_dirt, ps * 0.9).r * 2.0;
	float nr = texture(noise, ps * 0.2).r;
	vec3 rock = mix(rock_dark, rock_light, smoothstep(0.25, 0.85, nr * 0.6 + n1 * 0.4));
	rock *= (0.80 + 0.20 * smoothstep(0.3, 0.7, sin(wpos.y * 14.0 + nr * 5.0) * 0.5 + 0.5));
	rock *= mix(1.0, sr, detail);

	float wf = wgt.r, ws = wgt.g, wsw = wgt.b, wm = wgt.a;
	float wg = max(0.0, 1.0 - wf - ws - wsw - wm);
	vec3 col = (grass * wg + forest * wf + sand * ws + swamp * wsw + rock * wm)
		/ max(0.001, wg + wf + ws + wsw + wm);
	// Steile Flanken sind Fels, egal welche Art.
	float slope = 1.0 - clamp(wnrm.y, 0.0, 1.0);
	col = mix(col, rock, smoothstep(0.30, 0.55, slope + (n2 - 0.5) * 0.1));
	// Unter dem Wasserspiegel: Uferkies, nach unten dunkler.
	float under = smoothstep(water_level + 0.03, water_level - 0.05, wpos.y);
	col = mix(col, shore_col * (0.8 + 0.4 * n2), under);
	col *= mix(1.0, 0.55, smoothstep(water_level - 0.05, water_level - 0.30, wpos.y));

	// Nebel: Schleier, erkundet, ausser Reichweite, erreichbar.
	float v = fog_at(wpos.xz);
	float lit = mix(0.48, 1.0, smoothstep(0.5, 1.0, v));
	col *= lit;
	vec3 shroud = mix(shroud_dark, shroud_light,
		smoothstep(0.35, 0.75, texture(noise, p * 0.06 + vec2(TIME * 0.004, 0.0)).r));
	col = mix(shroud, col, smoothstep(0.05, 0.35, v));

	ALBEDO = col;
	ROUGHNESS = 0.95;
	SPECULAR = 0.2;
}
