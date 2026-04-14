import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE = "https://chummy-starboard-avid.ngrok-free.dev";
const NGROK_HEADERS = { "ngrok-skip-browser-warning": "true" };
const LIVE_IMAGE_URL = `${API_BASE}/latest-lot-image`;
const FALLBACK_LIVE_IMAGE = "/parking/engineering-live-view.png";

// Memphis, TN
const WEATHER_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=35.1495&longitude=-90.049&current=temperature_2m,weather_code,is_day&temperature_unit=fahrenheit&timezone=America%2FChicago";

const LOT_LAYOUT = {
  front: [
    "PS1",
    "PS2",
    "PS3",
    "PS4",
    "PS5",
    "PS6",
    "PS7",
    "PS8",
    "PS9",
    "PS10",
    "PS11",
  ],
  middle: [
    "PS12",
    "PS13",
    "PS14",
    "PS15",
    "PS16",
    "PS17",
    "PS18",
    "PS19",
    "PS20",
    "PS21",
    "PS22",
  ],
  upper: [
    "PS23",
    "PS24",
    "PS25",
    "PS26",
    "PS27",
    "PS28",
    "PS29",
    "PS30",
    "PS31",
    "PS32",
  ],
  backTop: ["PS33", "PS34", "PS35", "PS36", "PS37", "PS38", "PS39", "PS40"],
};

const ACCESSIBLE_SPOTS = new Set(["PS30", "PS31", "PS32", "PS39", "PS40"]);

function CarIcon() {
  return (
    <div className="relative h-8 w-14">
      <div className="absolute inset-x-1 top-1 h-6 rounded-[12px] bg-[#D95C59]" />
      <div className="absolute left-3 right-3 top-2.5 h-3 rounded-[8px] bg-[#F5B7B5]" />
      <div className="absolute -top-0.5 left-2 h-2.5 w-2.5 rounded-full bg-[#3D3D3D]" />
      <div className="absolute -top-0.5 right-2 h-2.5 w-2.5 rounded-full bg-[#3D3D3D]" />
      <div className="absolute -bottom-0.5 left-2 h-2.5 w-2.5 rounded-full bg-[#3D3D3D]" />
      <div className="absolute -bottom-0.5 right-2 h-2.5 w-2.5 rounded-full bg-[#3D3D3D]" />
    </div>
  );
}

function computeDirections(selectedSpot) {
  if (!selectedSpot) return [];

  const steps = ["Start at the gate on the far left."];

  if (selectedSpot.rowKey === "front") {
    steps.push("Move right into the front drive lane.");
    steps.push(`Continue straight until you reach ${selectedSpot.id}.`);
  } else if (selectedSpot.rowKey === "middle") {
    steps.push("Move right into the main center lane.");
    steps.push("Turn upward toward the middle row.");
    steps.push(`Continue to ${selectedSpot.id}.`);
  } else if (selectedSpot.rowKey === "upper") {
    steps.push("Move right along the upper access lane.");
    steps.push(`Continue straight to ${selectedSpot.id}.`);
  } else {
    steps.push("Move right toward the back row by the building.");
    steps.push(`Continue straight to ${selectedSpot.id}.`);
  }

  steps.push("You have arrived at your destination.");
  return steps;
}

function buildStructuredRows(statusMap) {
  return Object.entries(LOT_LAYOUT).map(([rowKey, ids]) => ({
    key: rowKey,
    spots: ids.map((id) => ({
      id,
      rowKey,
      status: statusMap.get(id) ?? "unknown",
      accessible: ACCESSIBLE_SPOTS.has(id),
    })),
  }));
}

function getWeatherInfo(weatherCode, isDay) {
  const day = Number(isDay) === 1;

  const map = {
    0: { label: "Clear", icon: day ? "☀️" : "🌙" },
    1: { label: "Mostly Clear", icon: day ? "🌤️" : "🌙" },
    2: { label: "Partly Cloudy", icon: "⛅" },
    3: { label: "Cloudy", icon: "☁️" },
    45: { label: "Fog", icon: "🌫️" },
    48: { label: "Fog", icon: "🌫️" },
    51: { label: "Light Drizzle", icon: "🌦️" },
    53: { label: "Drizzle", icon: "🌦️" },
    55: { label: "Heavy Drizzle", icon: "🌧️" },
    56: { label: "Freezing Drizzle", icon: "🌧️" },
    57: { label: "Freezing Drizzle", icon: "🌧️" },
    61: { label: "Light Rain", icon: "🌦️" },
    63: { label: "Rain", icon: "🌧️" },
    65: { label: "Heavy Rain", icon: "🌧️" },
    66: { label: "Freezing Rain", icon: "🌧️" },
    67: { label: "Freezing Rain", icon: "🌧️" },
    71: { label: "Light Snow", icon: "🌨️" },
    73: { label: "Snow", icon: "🌨️" },
    75: { label: "Heavy Snow", icon: "❄️" },
    77: { label: "Snow Grains", icon: "❄️" },
    80: { label: "Rain Showers", icon: "🌦️" },
    81: { label: "Rain Showers", icon: "🌧️" },
    82: { label: "Heavy Showers", icon: "⛈️" },
    85: { label: "Snow Showers", icon: "🌨️" },
    86: { label: "Snow Showers", icon: "🌨️" },
    95: { label: "Thunderstorm", icon: "⛈️" },
    96: { label: "Thunderstorm", icon: "⛈️" },
    99: { label: "Thunderstorm", icon: "⛈️" },
  };

  return map[weatherCode] || { label: "Weather", icon: "🌤️" };
}

export default function EngineeringFacultyLotPage() {
  const navigate = useNavigate();

  const [viewMode, setViewMode] = useState("map");
  const [selectedSpotId, setSelectedSpotId] = useState(null);
  const [dateTime, setDateTime] = useState(new Date());
  const [apiSpots, setApiSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [apiError, setApiError] = useState("");
  const [liveImageOk, setLiveImageOk] = useState(true);
  const [liveImageTick, setLiveImageTick] = useState(Date.now());

  const [weather, setWeather] = useState({
    temp: null,
    label: "Loading...",
    icon: "🌤️",
  });

  const mapFrameRef = useRef(null);
  const [mapScale, setMapScale] = useState(1);

  const BASE_MAP_WIDTH = 980;
  const BASE_MAP_HEIGHT = 430;

  useEffect(() => {
    const timer = setInterval(() => setDateTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    function updateMapScale() {
      if (!mapFrameRef.current) return;

      const frameWidth = mapFrameRef.current.clientWidth;
      const frameHeight = mapFrameRef.current.clientHeight;

      const scaleX = frameWidth / BASE_MAP_WIDTH;
      const scaleY = frameHeight / BASE_MAP_HEIGHT;

      setMapScale(Math.min(scaleX, scaleY, 1));
    }

    updateMapScale();
    window.addEventListener("resize", updateMapScale);

    return () => window.removeEventListener("resize", updateMapScale);
  }, []);

  useEffect(() => {
    let active = true;

    async function loadSpots() {
      try {
        const response = await fetch(`${API_BASE}/spots`, {
          headers: NGROK_HEADERS,
        });

        if (!response.ok) {
          throw new Error(`Failed to load spots: ${response.status}`);
        }

        const data = await response.json();

        if (!active) return;

        setApiSpots(Array.isArray(data) ? data : []);
        setApiError("");
        setLoading(false);
        setLiveImageTick(Date.now());
      } catch (error) {
        if (!active) return;
        console.error("Error loading spots:", error);
        setApiError("Could not load live parking data.");
        setLoading(false);
      }
    }

    loadSpots();
    const interval = setInterval(loadSpots, 300000); // 5 minutes

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let active = true;

    async function loadWeather() {
      try {
        const response = await fetch(WEATHER_URL);
        if (!response.ok) {
          throw new Error(`Failed to load weather: ${response.status}`);
        }

        const data = await response.json();
        if (!active) return;

        const current = data?.current;
        const info = getWeatherInfo(
          current?.weather_code,
          current?.is_day
        );

        setWeather({
          temp:
            typeof current?.temperature_2m === "number"
              ? Math.round(current.temperature_2m)
              : null,
          label: info.label,
          icon: info.icon,
        });
      } catch (error) {
        if (!active) return;
        console.error("Error loading weather:", error);
        setWeather({
          temp: null,
          label: "Unavailable",
          icon: "🌤️",
        });
      }
    }

    loadWeather();
    const interval = setInterval(loadWeather, 600000); // 10 minutes

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const statusMap = useMemo(() => {
    const map = new Map();

    for (const spot of apiSpots) {
      map.set(
        spot.label,
        spot.status === "occupied" ? "occupied" : "empty"
      );
    }

    return map;
  }, [apiSpots]);

  const structuredRows = useMemo(() => {
    return buildStructuredRows(statusMap);
  }, [statusMap]);

  const allStructuredSpots = useMemo(
    () =>
      structuredRows.flatMap((row) =>
        row.spots.map((spot) => ({
          ...spot,
          rowTitle: row.key,
        }))
      ),
    [structuredRows]
  );

  const selectedSpot =
    allStructuredSpots.find((spot) => spot.id === selectedSpotId) || null;

  const directions = useMemo(
    () => computeDirections(selectedSpot),
    [selectedSpot]
  );

  const stats = useMemo(() => {
    const free = allStructuredSpots.filter((s) => s.status === "empty").length;
    const occupied = allStructuredSpots.filter((s) => s.status === "occupied").length;
    const total = allStructuredSpots.length;
    const accessibility = allStructuredSpots.filter((s) => s.accessible).length;

    return { free, occupied, total, accessibility };
  }, [allStructuredSpots]);

  const freeSpots = allStructuredSpots.filter((s) => s.status === "empty");

  const formattedTime = dateTime.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const formattedDate = dateTime.toLocaleDateString([], {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  const rowYMap = {
    backTop: 78,
    upper: 168,
    middle: 258,
    front: 346,
  };

  const rowStartMap = {
    backTop: 375,
    upper: 170,
    middle: 135,
    front: 135,
  };

  const rowGapMap = {
    backTop: 10,
    upper: 12,
    middle: 12,
    front: 12,
  };

  const selectedPosition = useMemo(() => {
    if (!selectedSpot) return null;

    const row = structuredRows.find((r) => r.key === selectedSpot.rowKey);
    if (!row) return null;

    const index = row.spots.findIndex((s) => s.id === selectedSpot.id);
    if (index < 0) return null;

    const width =
      selectedSpot.rowKey === "backTop" ? 42 : selectedSpot.rowKey === "upper" ? 52 : 58;

    const height =
      selectedSpot.rowKey === "backTop" ? 62 : selectedSpot.rowKey === "upper" ? 76 : 92;

    const gap = rowGapMap[selectedSpot.rowKey];
    const startX = rowStartMap[selectedSpot.rowKey];
    const y = rowYMap[selectedSpot.rowKey];
    const x = startX + index * (width + gap);

    return { x, y, width, height };
  }, [selectedSpot, structuredRows]);
  
  return (
    <div className="min-h-screen bg-[#F2ECE1] text-[#6F4A2E]">
      <header className="border-b border-[#E6C4B7] bg-white/85 backdrop-blur-sm">
        <div className="mx-auto flex min-h-[88px] max-w-7xl items-center justify-between px-6 lg:px-10">
          <div className="flex items-center gap-3">
            <img
              src="/uofm-logo.jpg"
              alt="University of Memphis Logo"
              className="h-16 w-auto object-contain"
            />
            <img
              src="/adman-logo.png"
              alt="ADMAN Logo"
              className="h-16 w-auto object-contain"
            />
            <div className="flex flex-col justify-center leading-tight">
              <p className="text-base font-semibold tracking-[0.28em] text-[#2F4F4F]">
                ADMAN
              </p>
              <p className="text-sm tracking-[0.2em] text-[#2F4F4F]">
                Technologies
              </p>
            </div>
          </div>

          <div className="text-right">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-[#003087]">
              University of Memphis
            </p>
            <p className="font-serif text-2xl text-[#6F4A2E]">S.P.G.S</p>
            <p className="text-sm tracking-[0.14em] text-[#2F4F4F]">
              Smart Parking Guidance System
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1480px] px-5 py-6">
        <div className="grid grid-cols-[220px_minmax(0,1fr)_250px] gap-5">
          <aside className="flex flex-col gap-5">
            <div className="rounded-[2rem] bg-[#F7F2EB] p-5 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
              <p className="text-4xl font-light leading-tight text-[#1F5E95]">
                Live Time
              </p>
              <p className="mt-2 text-3xl font-semibold text-[#1F5E95]">
                {formattedTime}
              </p>
              <p className="mt-5 text-3xl font-light leading-tight text-[#1F5E95]">
                Current Date
              </p>
              <p className="mt-2 text-base font-medium text-[#2F4F4F]">
                {formattedDate}
              </p>
            </div>

            <div className="rounded-[2rem] bg-[#F7F2EB] p-5 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#1F5E95]">
                # Available Spots
              </p>

              <div className="mt-4 flex flex-wrap gap-2">
                {freeSpots.map((spot) => (
                  <button
                    key={spot.id}
                    onClick={() => setSelectedSpotId(spot.id)}
                    className={`rounded-lg border px-3 py-2 text-xs font-semibold transition ${
                      selectedSpotId === spot.id
                        ? "border-[#003087] bg-[#003087] text-white"
                        : "border-[#A8D5B4] bg-[#E8F7EC] text-[#2E8B57]"
                    }`}
                  >
                    {spot.id}
                  </button>
                ))}
              </div>

              <p className="mt-6 text-center text-lg font-medium text-[#4D88B3]">
                Available Parking
              </p>
            </div>
          </aside>

          <section className="rounded-[2.25rem] bg-[#F7F2EB] p-6 shadow-[0_12px_35px_rgba(0,0,0,0.06)]">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-5xl font-bold text-[#1F5E95]">
                  Smart Parking Guidance System
                </h1>
                <p className="mt-3 text-2xl text-[#4D88B3]">
                  Engineering Faculty Lot
                </p>
                {loading && (
                  <p className="mt-2 text-sm text-[#6A7C87]">Loading live status…</p>
                )}
                {apiError && (
                  <p className="mt-2 text-sm text-[#C65B57]">{apiError}</p>
                )}
              </div>

              <div className="flex gap-2">
                <button
                  onClick={() => setViewMode("map")}
                  className={`rounded-md px-3 py-2 text-xs font-semibold ${
                    viewMode === "map"
                      ? "bg-[#1F5E95] text-white"
                      : "border border-[#A7C5DF] bg-white text-[#1F5E95]"
                  }`}
                >
                  Map View
                </button>
                <button
                  onClick={() => setViewMode("live")}
                  className={`rounded-md px-3 py-2 text-xs font-semibold ${
                    viewMode === "live"
                      ? "bg-[#1F5E95] text-white"
                      : "border border-[#A7C5DF] bg-white text-[#1F5E95]"
                  }`}
                >
                  Live View
                </button>
              </div>
            </div>

            <div className="mt-6 rounded-[2rem] border-4 border-[#2C6DA4] bg-[#ECE8EA] p-4">
              <div
                ref={mapFrameRef}
                className="relative w-full overflow-hidden rounded-[1.5rem] bg-[#5E5B5B]"
                style={{ height: "min(430px, 55vw)" }}
              >
                {viewMode === "map" ? (
                  <div className="absolute inset-0 flex items-center justify-center overflow-hidden">
                    <div
                      className="relative"
                      style={{
                        width: `${BASE_MAP_WIDTH}px`,
                        height: `${BASE_MAP_HEIGHT}px`,
                        transform: `scale(${mapScale})`,
                        transformOrigin: "center center",
                      }}
                    >
                      <div className="absolute inset-0 rounded-[1.5rem] bg-[#5E5B5B]" />

                      <div className="absolute left-[120px] top-[96px] h-[42px] w-[620px] rounded-full bg-[#6B6666]" />
                      <div className="absolute left-[120px] top-[186px] h-[42px] w-[730px] rounded-full bg-[#6B6666]" />
                      <div className="absolute left-[120px] top-[276px] h-[42px] w-[730px] rounded-full bg-[#6B6666]" />
                      <div className="absolute left-[120px] top-[364px] h-[42px] w-[730px] rounded-full bg-[#6B6666]" />

                      <div className="absolute left-[55px] top-[110px] h-[40px] w-[2px] bg-white/80" />
                      <div className="absolute left-[55px] top-[200px] h-[42px] w-[2px] bg-white/80" />
                      <div className="absolute left-[55px] top-[290px] h-[42px] w-[2px] bg-white/80" />
                      <div className="absolute left-[55px] top-[378px] h-[42px] w-[2px] bg-white/80" />

                      <div className="absolute left-4 top-[295px] flex items-center gap-2">
                        <div className="rounded-full bg-[#1A318A] px-4 py-2 text-lg font-bold text-white">
                          Gate
                        </div>
                      </div>

                      {selectedPosition && (
                        <>
                          {/* from gate down into bottom drive lane */}
                          <div
                            className="absolute w-1 rounded-full bg-[#1A318A]"
                            style={{
                              left: 120,
                              top: 315,
                              height: 55,
                            }}
                          />

                          {/* across the bottom drive lane */}
                          <div
                            className="absolute h-1 rounded-full bg-[#1A318A]"
                            style={{
                              left: 120,
                              top: 370,
                              width: Math.max(20, selectedPosition.x - 120),
                            }}
                          />

                          {/* go up only when needed */}
                          {selectedSpot?.rowKey !== "front" && (
                            <div
                              className="absolute w-1 rounded-full bg-[#1A318A]"
                              style={{
                                left: selectedPosition.x,
                                top: selectedPosition.y + 46,
                                height: Math.max(10, 370 - (selectedPosition.y + 46)),
                              }}
                            />
                          )}

                          {/* arrow head */}
                          <div
                            className={`absolute h-0 w-0 border-y-[7px] border-l-[12px] border-y-transparent border-l-[#1A318A] ${
                              selectedSpot?.rowKey === "front" ? "" : "-rotate-90"
                            }`}
                            style={{
                              left: selectedSpot?.rowKey === "front" ? selectedPosition.x + 2 : selectedPosition.x - 4,
                              top: selectedSpot?.rowKey === "front" ? 364 : selectedPosition.y + 34,
                            }}
                          />
                        </>
                      )}

                      <div className="absolute inset-0">
                        {structuredRows.map((row) => {
                          const rowY = rowYMap[row.key] ?? 170;
                          const startX = rowStartMap[row.key] ?? 100;
                          const gap = rowGapMap[row.key] ?? 10;

                          return row.spots.map((spot, index) => {
                            const isFree = spot.status === "empty";
                            const isSelected = selectedSpotId === spot.id;

                            const width =
                              row.key === "backTop"
                                ? 42
                                : row.key === "upper"
                                ? 52
                                : 58;

                            const height =
                              row.key === "backTop"
                                ? 62
                                : row.key === "upper"
                                ? 76
                                : 92;

                            const x = startX + index * (width + gap);

                            return (
                              <button
                                key={spot.id}
                                onClick={() => isFree && setSelectedSpotId(spot.id)}
                                className={`absolute flex flex-col items-center justify-center rounded-[12px] border-2 transition ${
                                  isSelected
                                    ? "border-[#1A318A] ring-4 ring-[#1A318A]/20"
                                    : "border-white/80"
                                } ${
                                  isFree
                                    ? "bg-[#A9CDAE] hover:scale-105"
                                    : "bg-[#E6C9C9]"
                                } ${isFree ? "cursor-pointer" : "cursor-default"}`}
                                style={{
                                  left: x,
                                  top: rowY,
                                  width,
                                  height,
                                }}
                              >
                                {spot.accessible && (
                                  <span className="absolute -top-2 right-1 rounded-full bg-[#1A318A] px-2 py-0.5 text-[10px] font-bold text-white">
                                    A
                                  </span>
                                )}

                                {isFree ? (
                                  <>
                                    <span
                                      className={`font-semibold text-[#2E7B50] ${
                                        row.key === "backTop" ? "text-xs" : "text-sm"
                                      }`}
                                    >
                                      FREE
                                    </span>
                                    <span className="mt-1 text-[11px] font-medium text-[#2F4F4F]">
                                      {spot.id}
                                    </span>
                                  </>
                                ) : (
                                  <>
                                    <CarIcon />
                                    <span className="mt-1 text-[11px] font-medium text-[#6F4A2E]">
                                      {spot.id}
                                    </span>
                                  </>
                                )}
                              </button>
                            );
                          });
                        })}
                      </div>
                    </div>
                  </div>
                ) : (
                  <img
                    src={
                      liveImageOk
                        ? `${LIVE_IMAGE_URL}?t=${liveImageTick}`
                        : FALLBACK_LIVE_IMAGE
                    }
                    onError={() => setLiveImageOk(false)}
                    alt="Engineering Faculty Lot Live View"
                    className="h-full w-full rounded-[1.5rem] object-cover"
                  />
                )}
              </div>
            </div>
          </section>

          <aside className="flex flex-col gap-5">
            <div className="rounded-[2rem] bg-[#F7F2EB] p-5 text-center shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
              <div className="mx-auto mb-3 flex h-20 w-20 items-center justify-center rounded-full bg-[#F8EAB7] text-4xl">
                {weather.icon}
              </div>
              <p className="text-2xl font-medium text-[#3D88B9]">Memphis Weather</p>
              <p className="mt-2 text-base text-[#2F4F4F]">
                {weather.label}
                {weather.temp !== null ? ` • ${weather.temp}°F` : ""}
              </p>
            </div>

            <div className="rounded-[2rem] bg-[#F7F2EB] p-5 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
              <p className="text-center text-2xl font-medium text-[#3D88B9]">
                Directions
              </p>

              <div className="mt-4 min-h-[210px] rounded-[1.75rem] border-2 border-[#9CC0E0] bg-white p-4">
                {selectedSpot ? (
                  <div className="space-y-3">
                    <p className="text-sm font-semibold text-[#1A318A]">
                      Destination: {selectedSpot.id}
                    </p>

                    {directions.map((step, index) => (
                      <div
                        key={index}
                        className="rounded-xl bg-[#F6F2EC] px-3 py-2 text-sm text-[#2F4F4F]"
                      >
                        <span className="mr-2 font-bold text-[#1A318A]">
                          {index + 1}.
                        </span>
                        {step}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex h-full min-h-[180px] items-center justify-center text-center text-sm text-[#5D6F7B]">
                    Select an available space to see directions.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[2rem] bg-[#F7F2EB] p-5 shadow-[0_10px_30px_rgba(0,0,0,0.05)]">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-[#1A318A]">
                Lot Summary
              </p>

              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between rounded-xl bg-[#E8F7EC] px-4 py-3">
                  <span>Free</span>
                  <span className="font-bold text-[#2E8B57]">{stats.free}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-[#FDEAEA] px-4 py-3">
                  <span>Occupied</span>
                  <span className="font-bold text-[#D9534F]">{stats.occupied}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-[#EEF3FA] px-4 py-3">
                  <span>Total</span>
                  <span className="font-bold text-[#1A318A]">{stats.total}</span>
                </div>
                <div className="flex items-center justify-between rounded-xl bg-[#F6F1EB] px-4 py-3">
                  <span>Accessibility</span>
                  <span className="font-bold text-[#6F4A2E]">
                    {stats.accessibility}
                  </span>
                </div>
              </div>
            </div>
          </aside>
        </div>

        <div className="mt-6 flex justify-center">
          <button
            onClick={() => navigate("/select-lot")}
            className="rounded-full border-2 border-[#E6C4B7] bg-[#FCDDD3] px-8 py-3 text-base font-semibold tracking-[0.14em] text-[#6F4A2E] transition hover:bg-[#E6C4B7]"
          >
            Back to Lots
          </button>
        </div>
      </main>
    </div>
  );
}