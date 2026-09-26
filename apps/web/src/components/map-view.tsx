"use client";

import type { PickingInfo } from "@deck.gl/core";
import { GoogleMapsOverlay } from "@deck.gl/google-maps";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { APIProvider, ColorScheme, Map as GoogleMap, useMap } from "@vis.gl/react-google-maps";
import { useEffect, useMemo, useRef } from "react";

import { assetValue, type ColorBy, kindLabel, percent, type Rgb, riskColor } from "@/lib/format";
import type { Asset, ForecastAsset, Region, StormPosition, TrackFeatureCollection } from "@/lib/types";

type Path = { id: string; path: [number, number][] };

interface MapViewProps {
  apiKey: string;
  region: Region;
  assets: (Asset | ForecastAsset)[];
  colorBy: ColorBy;
  windById: Map<string, number> | null;
  track: TrackFeatureCollection | undefined;
  members: TrackFeatureCollection | undefined;
  storm: StormPosition | null;
  selectedId: string | null;
  onSelect: (assetId: string | null) => void;
}

const WHITE: Rgb = [255, 255, 255];
const MEMBER_BLUE: [number, number, number, number] = [57, 135, 229, 110];
const STORM_RED: Rgb = [208, 59, 59];

function lines(collection: TrackFeatureCollection | undefined): Path[] {
  return (collection?.features ?? [])
    .filter((f) => f.geometry.type === "LineString")
    .map((f, i) => ({ id: String(f.properties.member ?? i), path: f.geometry.coordinates as [number, number][] }));
}

function DeckOverlay({ layers, tooltip }: { layers: unknown[]; tooltip: (info: PickingInfo) => string | null }) {
  const map = useMap();
  const overlay = useRef<GoogleMapsOverlay | null>(null);
  const latest = useRef({ layers, tooltip });

  // Attach only once the map knows its rendering type. Given an UNINITIALIZED map, deck.gl registers a
  // `renderingtype_changed` listener it never removes, so after an unmount (React's dev double-mount) that listener
  // builds an overlay on the finalized instance. Our own listener is removed on cleanup, and each mount owns one
  // overlay that finalize() fully tears down.
  useEffect(() => {
    if (!map) return;
    let instance: GoogleMapsOverlay | null = null;
    const attach = () => {
      instance = new GoogleMapsOverlay({ interleaved: true });
      instance.setProps({ layers: latest.current.layers as never[], getTooltip: latest.current.tooltip });
      instance.setMap(map);
      overlay.current = instance;
    };
    let listener: google.maps.MapsEventListener | null = null;
    if (map.getRenderingType() !== google.maps.RenderingType.UNINITIALIZED) attach();
    else listener = map.addListener("renderingtype_changed", attach);
    return () => {
      listener?.remove();
      instance?.finalize();
      overlay.current = null;
    };
  }, [map]);

  useEffect(() => {
    latest.current = { layers, tooltip };
    overlay.current?.setProps({ layers: layers as never[], getTooltip: tooltip });
  }, [layers, tooltip]);
  return null;
}

function FitRegion({ region }: { region: Region }) {
  const map = useMap();
  useEffect(() => {
    const [south, west, north, east] = region.bbox;
    map?.fitBounds({ south, west, north, east }, 24);
  }, [map, region]);
  return null;
}

export function MapView(props: MapViewProps) {
  const { apiKey, region, assets, colorBy, windById, track, members, storm, selectedId, onSelect } = props;

  const layers = useMemo(() => {
    const assetLayer = new ScatterplotLayer<Asset | ForecastAsset>({
      id: "assets",
      data: [...assets].reverse(), // draw highest priority last so it sits on top
      getPosition: (a) => [a.lon, a.lat],
      getFillColor: (a) => [...riskColor(assetValue(a, colorBy, windById)), 200] as [number, number, number, number],
      getRadius: (a) => 2 + 3.5 * assetValue(a, colorBy, windById), // small enough that dense clusters stay legible
      getLineColor: (a) => (a.asset_id === selectedId ? [255, 255, 255, 255] : [20, 20, 20, 160]),
      getLineWidth: (a) => (a.asset_id === selectedId ? 2.5 : 0.6),
      radiusUnits: "pixels",
      lineWidthUnits: "pixels",
      stroked: true,
      pickable: true,
      onClick: (info) => onSelect(info.object ? info.object.asset_id : null),
      updateTriggers: {
        getFillColor: [colorBy, windById],
        getRadius: [colorBy, windById],
        getLineColor: selectedId,
        getLineWidth: selectedId,
      },
    });
    const memberLayer = new PathLayer<Path>({
      id: "ensemble",
      data: lines(members),
      getPath: (p) => p.path,
      getColor: MEMBER_BLUE,
      widthUnits: "pixels",
      getWidth: 1.5,
    });
    const trackLayer = new PathLayer<Path>({
      id: "best-track",
      data: members ? [] : lines(track),
      getPath: (p) => p.path,
      getColor: [...WHITE, 220] as [number, number, number, number],
      widthUnits: "pixels",
      getWidth: 2.5,
    });
    const stormLayer = new ScatterplotLayer<StormPosition>({
      id: "storm",
      data: storm ? [storm] : [],
      getPosition: (s) => [s.lon, s.lat],
      getRadius: (s) => s.rmw_km * 1000,
      radiusUnits: "meters",
      stroked: true,
      filled: true,
      getFillColor: [...STORM_RED, 40] as [number, number, number, number],
      getLineColor: [...STORM_RED, 255] as [number, number, number, number],
      lineWidthUnits: "pixels",
      getLineWidth: 2,
    });
    return [memberLayer, trackLayer, assetLayer, stormLayer];
  }, [assets, colorBy, windById, members, track, storm, selectedId, onSelect]);

  const tooltip = useMemo(
    () => (info: PickingInfo) => {
      const asset = info.object as Asset | ForecastAsset | undefined;
      if (!asset || info.layer?.id !== "assets") return null;
      const gales = "p34" in asset ? ` · gales ${percent(asset.p34)}` : "";
      return `#${asset.rank} ${asset.name ?? kindLabel(asset.kind)}\n${kindLabel(asset.kind)} · outage ${percent(asset.p_outage)}${gales}`;
    },
    [],
  );

  return (
    <APIProvider apiKey={apiKey}>
      <GoogleMap
        className="absolute inset-0" // size from the positioned parent: % heights collapse inside grid-stretched items
        mapId="DEMO_MAP_ID"
        colorScheme={ColorScheme.DARK}
        defaultCenter={{ lat: 20.3, lng: 86.0 }}
        defaultZoom={7}
        gestureHandling="greedy"
        disableDefaultUI
        zoomControl
      >
        <FitRegion region={region} />
        <DeckOverlay layers={layers} tooltip={tooltip} />
      </GoogleMap>
    </APIProvider>
  );
}
