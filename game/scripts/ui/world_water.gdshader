// Wasser der Weltkarte (It. 77): eine Flaeche auf Hoehe des Wasserspiegels
// ueber der ganzen Karte. Wo das Gelaende hoeher liegt, verdeckt es sie.
// Farbe tief/flach nach der Wassermaske (eine Zelle je Kachel, gefiltert):
// am Rand heller und mit Gischtsaum, in der Mitte dunkel. Nebel wie beim
// Gelaende aus derselben Textur.
shader_type spatial;
render_mode diffuse_burley, specular_schlick_ggx;

uniform sampler2D noise : repeat_enable, filter_linear;
uniform sampler2D fog_tex : filter_linear;
uniform sampler2D water_mask : filter_linear;
uniform vec2 map_size = vec2(18.0, 26.0);
uniform vec3 deep : source_color = vec3(0.10, 0.22, 0.34);
uniform vec3 shallow : source_color = vec3(0.22, 0.42, 0.50);
uniform vec3 foam : source_color = vec3(0.80, 0.86, 0.85);
uniform vec3 shroud_dark : source_color = vec3(0.05, 0.06, 0.08);

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv = clamp((wpos.xz + vec2(0.5)) / map_size, vec2(0.0), vec2(1.0));
	vec2 o = max(-(wpos.xz + vec2(0.5)), wpos.xz + vec2(0.5) - map_size);
	float inside = 1.0 - smoothstep(0.0, 1.2, max(o.x, o.y));
	float m = texture(water_mask, uv).r * inside;
	float v = texture(fog_tex, uv).r * inside;
	vec2 p = wpos.xz;
	float r1 = texture(noise, p * 0.35 + vec2(TIME * 0.010, TIME * 0.006)).r;
	float r2 = texture(noise, p * 0.80 - vec2(TIME * 0.012, 0.0)).r;
	vec3 col = mix(shallow, deep, smoothstep(0.55, 0.95, m));
	col *= 0.85 + 0.3 * r1;
	// Gischt am Ufer: dort, wo die Maske gerade kippt.
	float shore = smoothstep(0.30, 0.48, m) * (1.0 - smoothstep(0.48, 0.70, m));
	col = mix(col, foam, shore * smoothstep(0.45, 0.65, r2) * 0.8);
	col *= mix(0.48, 1.0, smoothstep(0.5, 1.0, v));
	col = mix(shroud_dark, col, smoothstep(0.05, 0.35, v));
	ALBEDO = col;
	ROUGHNESS = 0.15 + 0.2 * r2;
	METALLIC = 0.0;
	// Kein Glanz unter dem Schleier - sonst blitzt der Kartenrand.
	SPECULAR = 0.6 * smoothstep(0.05, 0.35, v);
}
