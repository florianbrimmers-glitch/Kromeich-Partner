// PILOT (It. 72): durchgehender Boden im Stil von Heroes 4.
//
// Vorher lag je Zelle eine einfarbige Kachel, auf dem Brett im Schachbrett.
// Heroes 4 hat kein sichtbares Raster: gemalter Boden, Gras mit helleren und
// dunkleren Flecken, Erdstellen mit weichem Rand. Das Raster erscheint dort
// nur, wenn eine Einheit ihre Reichweite zeigt.
//
// Alles haengt an der WELTlage, nicht an UVs: eine einzige grosse Flaeche,
// und die Flecken laufen ueber Zellgrenzen hinweg, wie in der Vorlage.
shader_type spatial;
render_mode diffuse_burley;

// STRUKTURKARTEN statt Fotos: das Werkzeug rechnet aus jedem Foto die
// reine Helligkeitsschwankung, normiert auf einen Mittelwert von 1.0 und
// gespeichert als Wert/2 (0.5 = Mittel). KEIN source_color - das sind
// Messwerte, keine Farben. Ein erster Anlauf teilte im Shader durch einen
// vorab gemessenen Mittelwert; Messung und Shader lagen in verschiedenen
// Farbraeumen, und das Feld kam weiss heraus.
uniform sampler2D detail_a : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_b : repeat_enable, filter_linear_mipmap;
uniform sampler2D detail_dirt : repeat_enable, filter_linear_mipmap;
uniform sampler2D noise : repeat_enable, filter_linear;
uniform float detail = 0.85;

// STRUKTUR AUS DEM FOTO, FARBE GEMALT. Echtes Gras ist auf Fotos olivbraun;
// die gruene Wiese von Heroes 4 ist gemalt. "Nicht ganz so realistisch"
// heisst: echte Kleinstruktur, gemalter Farbton. Gedeckt, nicht neon - der
// erste Palettenversuch leuchtete unter ACES und Saettigung 1.22.
uniform vec3 grass_dark : source_color = vec3(0.16, 0.27, 0.10);
uniform vec3 grass_mid : source_color = vec3(0.27, 0.40, 0.15);
uniform vec3 grass_light : source_color = vec3(0.40, 0.50, 0.22);
uniform vec3 grass_dry : source_color = vec3(0.47, 0.45, 0.25);
uniform vec3 dirt_col : source_color = vec3(0.40, 0.31, 0.21);

// Wiederholungen je Welteinheit (eine Zelle = 1).
uniform float tile_a = 0.33;
uniform float tile_b = 0.21;
uniform float tile_dirt = 0.28;
uniform float patch_scale = 0.055;
uniform float dirt_amount = 0.74;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float lum(vec3 c) {
	return dot(c, vec3(0.299, 0.587, 0.114));
}

void fragment() {
	vec2 p = wpos.xz;
	float sa = texture(detail_a, p * tile_a).r * 2.0;
	float sb = texture(detail_b, p * tile_b + vec2(0.37, 0.11)).r * 2.0;
	float sd = texture(detail_dirt, p * tile_dirt).r * 2.0;
	float sg = mix(sa, sb, 0.5);

	float n1 = texture(noise, p * patch_scale).r;
	float n2 = texture(noise, p * patch_scale * 2.7 + vec2(0.31, 0.77)).r;
	float n3 = texture(noise, p * patch_scale * 0.45 + vec2(0.53, 0.19)).r;

	// Grosse helle und dunkle Wiesenpartien - das traegt den Eindruck.
	float t = smoothstep(0.20, 0.80, n1 * 0.65 + n3 * 0.35);
	vec3 grass = t < 0.5 ? mix(grass_dark, grass_mid, t * 2.0)
	                     : mix(grass_mid, grass_light, t * 2.0 - 1.0);
	// Vereinzelt trockene Stellen.
	grass = mix(grass, grass_dry, smoothstep(0.66, 0.80, n2) * 0.55);
	grass *= mix(1.0, sg, detail);

	// Erdstellen mit ausgefranstem Rand.
	float d = smoothstep(dirt_amount, dirt_amount + 0.06, n1 + (n2 - 0.5) * 0.30);
	vec3 col = mix(grass, dirt_col * mix(1.0, sd, detail), d);

	ALBEDO = col;
	ROUGHNESS = 0.96;
	SPECULAR = 0.2;
}
