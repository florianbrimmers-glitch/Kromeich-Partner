using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading.Tasks;

namespace KromeichHeroes.Net;

// Minimal-Client fuer Supabase REST + Auth.
// Stub-Status: genug fuer ersten Smoke-Call. Noch ohne Realtime-WebSocket.
//
// Benutzung:
//   var client = new SupabaseClient("https://xyz.supabase.co", "anon-key");
//   await client.SignInWithOtpAsync("mail@example.com");
//   var match = await client.CreateMatchAsync(...);
public sealed class SupabaseClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _anonKey;
    private string? _accessToken;

    public SupabaseClient(string url, string anonKey)
    {
        _http = new HttpClient { BaseAddress = new Uri(url.TrimEnd('/') + "/") };
        _http.DefaultRequestHeaders.Add("apikey", anonKey);
        _anonKey = anonKey;
    }

    private void SetAuth(HttpRequestMessage req)
    {
        var tok = _accessToken ?? _anonKey;
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", tok);
    }

    // ---- Auth ----

    public async Task SignInWithOtpAsync(string email)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, "auth/v1/otp")
        {
            Content = JsonContent.Create(new { email, create_user = true }),
        };
        SetAuth(req);
        (await _http.SendAsync(req)).EnsureSuccessStatusCode();
    }

    public async Task VerifyOtpAsync(string email, string token)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, "auth/v1/verify")
        {
            Content = JsonContent.Create(new { type = "email", email, token }),
        };
        SetAuth(req);
        var resp = (await _http.SendAsync(req)).EnsureSuccessStatusCode();
        using var stream = await resp.Content.ReadAsStreamAsync();
        var doc = await JsonDocument.ParseAsync(stream);
        _accessToken = doc.RootElement.GetProperty("access_token").GetString();
    }

    // ---- Matches ----

    public async Task<Guid> CreateMatchAsync(string mapTemplate, ulong mapSeed, object initialStateJson)
    {
        var body = new
        {
            map_template = mapTemplate,
            map_seed = (long)mapSeed,
            state_json = initialStateJson,
        };
        var req = new HttpRequestMessage(HttpMethod.Post, "rest/v1/matches")
        {
            Content = JsonContent.Create(body),
        };
        req.Headers.Add("Prefer", "return=representation");
        SetAuth(req);
        var resp = (await _http.SendAsync(req)).EnsureSuccessStatusCode();
        var arr = await resp.Content.ReadFromJsonAsync<List<Dictionary<string, JsonElement>>>()
                  ?? throw new InvalidOperationException("Empty response");
        return Guid.Parse(arr[0]["id"].GetString()!);
    }

    public async Task SubmitMoveAsync(Guid matchId, int turn, int slot, object actionJson)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, "rest/v1/moves")
        {
            Content = JsonContent.Create(new
            {
                match_id = matchId,
                turn,
                slot,
                action_json = actionJson,
            }),
        };
        SetAuth(req);
        (await _http.SendAsync(req)).EnsureSuccessStatusCode();
    }

    public async Task<JsonElement> GetMatchStateAsync(Guid matchId)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, $"rest/v1/matches?id=eq.{matchId}&select=*");
        SetAuth(req);
        var resp = (await _http.SendAsync(req)).EnsureSuccessStatusCode();
        var arr = await resp.Content.ReadFromJsonAsync<List<JsonElement>>()
                  ?? throw new InvalidOperationException("Empty response");
        return arr[0];
    }

    public void Dispose() => _http.Dispose();
}
