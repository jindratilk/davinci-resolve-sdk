// Generated proprietary residual AV input schemas. Do not edit or publish.
export const SDK_RESIDUAL_AV_PREPARED_INPUTS = [
  {
    "actionId": "cutagent.action.audio.beat_detect",
    "operationClass": "mutation",
    "authority": "managed_file",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "barsPerPhrase": {
          "minimum": 1,
          "type": "integer"
        },
        "beatOffset": {
          "type": "integer"
        },
        "beatsPerBar": {
          "minimum": 1,
          "type": "integer"
        },
        "fps": {
          "exclusiveMinimum": 0,
          "type": "number"
        },
        "inputPath": {
          "minLength": 1,
          "type": "string"
        },
        "maxBpm": {
          "minimum": 1,
          "type": "number"
        },
        "minBpm": {
          "minimum": 1,
          "type": "number"
        }
      },
      "required": [
        "inputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.audio.duck",
    "operationClass": "mutation",
    "authority": "exact_media_revision_or_managed_file",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "attackMs": {
          "minimum": 0,
          "type": "number"
        },
        "inputPath": {
          "minLength": 1,
          "type": "string"
        },
        "musicTrackIndex": {
          "minimum": 1,
          "type": "integer"
        },
        "outputPath": {
          "minLength": 1,
          "type": "string"
        },
        "ratio": {
          "exclusiveMinimum": 0,
          "type": "number"
        },
        "releaseMs": {
          "minimum": 0,
          "type": "number"
        },
        "replaceMediaName": {
          "minLength": 1,
          "type": "string"
        },
        "speechTrackIndex": {
          "minimum": 1,
          "type": "integer"
        },
        "thresholdDb": {
          "type": "number"
        }
      },
      "required": [
        "inputPath",
        "speechTrackIndex",
        "musicTrackIndex"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.audio.info",
    "operationClass": "read",
    "authority": "managed_file",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "inputPath": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "inputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.audio.probe_subframe",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "force": {
          "type": "boolean"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.audio.reverb",
    "operationClass": "mutation",
    "authority": "managed_file",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "inputPath": {
          "minLength": 1,
          "type": "string"
        },
        "outputPath": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "inputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.audio.waveform_offset",
    "operationClass": "mutation",
    "authority": "managed_file",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "fps": {
          "exclusiveMinimum": 0,
          "type": "number"
        },
        "priorOffsetSeconds": {
          "type": "number"
        },
        "referencePath": {
          "minLength": 1,
          "type": "string"
        },
        "targetPath": {
          "minLength": 1,
          "type": "string"
        },
        "useMetadata": {
          "type": "boolean"
        },
        "windowCount": {
          "minimum": 1,
          "type": "integer"
        },
        "windowSeconds": {
          "exclusiveMinimum": 0,
          "type": "number"
        }
      },
      "required": [
        "referencePath",
        "targetPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.burnin.load",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "presetName": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "presetName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.burnin.preset.export",
    "operationClass": "mutation",
    "authority": "exact_project_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "outputPath": {
          "minLength": 1,
          "type": "string"
        },
        "presetName": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "presetName",
        "outputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.burnin.preset.import",
    "operationClass": "mutation",
    "authority": "exact_project_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "inputPath": {
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "inputPath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.audio_eq",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "band": {
          "type": "integer"
        },
        "filterType": {
          "type": "string"
        },
        "freq": {
          "type": "integer"
        },
        "gainDb": {
          "type": "number"
        },
        "name": {
          "type": "string"
        },
        "preset": {
          "type": "string"
        },
        "q": {
          "type": "number"
        },
        "uiBand": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.audio_gain",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "db": {
          "type": "number"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [
        "db"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.audio_normalize",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "targetDbfs": {
          "type": "number"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.audio_pan",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "value": {
          "type": "number"
        }
      },
      "required": [
        "value"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.audio_pitch",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "cents": {
          "type": "integer"
        },
        "name": {
          "type": "string"
        },
        "semitones": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.burnin.load",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "clipOrName": {
          "type": "string"
        },
        "maybeName": {
          "type": "string"
        }
      },
      "required": [
        "clipOrName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.cache",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "cacheType": {
          "type": "string"
        },
        "enable": {
          "type": "boolean"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.cache_set",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "cacheType": {
          "type": "string"
        },
        "clip": {
          "type": "string"
        },
        "mode": {
          "type": "string"
        }
      },
      "required": [
        "mode"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.color",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clear": {
          "type": "boolean"
        },
        "name": {
          "type": "string"
        },
        "set": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.composite",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "mode": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "opacityVal": {
          "type": "number"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.disable",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.dynamic_zoom",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "ease": {
          "type": "string"
        },
        "end": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "sourceIn": {
          "type": "string"
        },
        "sourceOut": {
          "type": "string"
        },
        "start": {
          "type": "string"
        }
      },
      "required": [
        "end",
        "start"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.enable",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fade_in",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "at": {
          "type": "string"
        },
        "audioDuration": {
          "type": "string"
        },
        "duration": {
          "type": "string"
        },
        "edge": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "scope": {
          "type": "string"
        },
        "videoDuration": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.flag",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "add": {
          "type": "string"
        },
        "clear": {
          "type": "boolean"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.add",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.delete",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "index": {
          "type": "integer"
        },
        "name": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.export",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "index": {
          "type": "integer"
        },
        "path": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [
        "index",
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.import",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "path": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        }
      },
      "required": [
        "path"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.list",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        },
        "recordFrame": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.load",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "comp": {
          "type": "string"
        }
      },
      "required": [
        "clip",
        "comp"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.fusion.tool_set",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "compIndex": {
          "type": "integer"
        },
        "inputName": {
          "type": "string"
        },
        "recordFrame": {
          "type": "string"
        },
        "toolName": {
          "type": "string"
        },
        "track": {
          "type": "integer"
        },
        "value": {
          "type": "string"
        }
      },
      "required": [
        "inputName",
        "toolName",
        "value"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.link",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_set_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clips": {
          "items": {
            "type": "string"
          },
          "type": "array"
        }
      },
      "required": [
        "clips"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.linked.list",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.add",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "color": {
          "type": "string"
        },
        "duration": {
          "type": "integer"
        },
        "frame": {
          "type": "integer"
        },
        "frameDomain": {
          "type": "string"
        },
        "markerName": {
          "type": "string"
        },
        "note": {
          "type": "string"
        }
      },
      "required": [
        "frame"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.custom_data",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "clipOrFrame": {
          "type": "string"
        },
        "frameOrData": {
          "type": "string"
        },
        "maybeData": {
          "type": "string"
        }
      },
      "required": [
        "clipOrFrame",
        "frameOrData"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.delete",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "frame": {
          "type": "integer"
        },
        "frameDomain": {
          "type": "string"
        }
      },
      "required": [
        "frame"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.marker.delete_custom",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "clipOrData": {
          "type": "string"
        },
        "maybeData": {
          "type": "string"
        }
      },
      "required": [
        "clipOrData"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.offset",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "clipName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.properties",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "key": {
          "type": "string"
        },
        "name": {
          "type": "string"
        },
        "setKey": {
          "type": "string"
        },
        "setValue": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.rename",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "newName": {
          "type": "string"
        },
        "oldName": {
          "type": "string"
        }
      },
      "required": [
        "newName",
        "oldName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.reset_node_colors",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.smart_reframe",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "anyOf": [
        {
          "properties": {
            "timelineItemId": {
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "timelineItemId"
          ]
        },
        {
          "properties": {
            "clipName": {
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "clipName"
          ]
        },
        {
          "properties": {
            "recordFrame": {
              "minLength": 1,
              "type": "string"
            },
            "trackIndex": {
              "minimum": 1,
              "type": "integer"
            }
          },
          "required": [
            "trackIndex",
            "recordFrame"
          ]
        }
      ],
      "dependentRequired": {
        "recordFrame": [
          "trackIndex"
        ],
        "trackIndex": [
          "recordFrame"
        ]
      },
      "not": {
        "anyOf": [
          {
            "required": [
              "timelineItemId",
              "trackIndex"
            ]
          },
          {
            "required": [
              "timelineItemId",
              "recordFrame"
            ]
          },
          {
            "required": [
              "clipName",
              "timelineItemId"
            ]
          },
          {
            "required": [
              "clipName",
              "trackIndex"
            ]
          },
          {
            "required": [
              "clipName",
              "recordFrame"
            ]
          }
        ]
      },
      "properties": {
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "operationId": {
          "minLength": 1,
          "type": "string"
        },
        "recordFrame": {
          "minLength": 1,
          "type": "string"
        },
        "timelineItemId": {
          "minLength": 1,
          "type": "string"
        },
        "trackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "operationId"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.source_range",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.stabilize",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.take.add",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "endFrame": {
          "type": "integer"
        },
        "mediaName": {
          "type": "string"
        },
        "startFrame": {
          "type": "integer"
        }
      },
      "required": [
        "mediaName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.take.delete",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        },
        "index": {
          "type": "integer"
        }
      },
      "required": [
        "clip",
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.take.finalize",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.take.list",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.take.select",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        },
        "index": {
          "type": "integer"
        }
      },
      "required": [
        "index"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.track_info",
    "operationClass": "read",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.unlink",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_set_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clipName": {
          "type": "string"
        }
      },
      "required": [
        "clipName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.update_sidecar",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "clip": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.clip.voice_isolation",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "amount": {
          "type": "integer"
        },
        "enable": {
          "type": "boolean"
        },
        "name": {
          "type": "string"
        }
      },
      "required": [],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.auto_subtitle",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "charsPerLine": {
          "maximum": 60,
          "minimum": 1,
          "type": "integer"
        },
        "gapFrames": {
          "maximum": 10,
          "minimum": 0,
          "type": "integer"
        },
        "language": {
          "maxLength": 64,
          "minLength": 1,
          "type": "string"
        },
        "lineBreak": {
          "enum": [
            "single",
            "double"
          ]
        },
        "preset": {
          "enum": [
            "default",
            "teletext",
            "netflix"
          ]
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "sourceAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "sourceAudioTargets"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.camera_pip",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "dependentRequired": {
        "marginPixels": [
          "anchor"
        ]
      },
      "properties": {
        "anchor": {
          "enum": [
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
            "center"
          ]
        },
        "backgroundMedia": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "id",
            "name"
          ],
          "type": "object"
        },
        "backgroundTrackIndex": {
          "maximum": 4096,
          "minimum": 1,
          "type": "integer"
        },
        "cameraMedia": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            }
          },
          "required": [
            "id",
            "name"
          ],
          "type": "object"
        },
        "cameraTrackIndex": {
          "maximum": 4096,
          "minimum": 1,
          "type": "integer"
        },
        "cornerRadius": {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        "durationFrames": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "type": "integer"
        },
        "marginPixels": {
          "maximum": 10000,
          "minimum": 0,
          "type": "number"
        },
        "opacity": {
          "maximum": 100,
          "minimum": 0,
          "type": "number"
        },
        "pan": {
          "maximum": 10,
          "minimum": -10,
          "type": "number"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordStartFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "softness": {
          "maximum": 1,
          "minimum": 0,
          "type": "number"
        },
        "tilt": {
          "maximum": 10,
          "minimum": -10,
          "type": "number"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "zoom": {
          "exclusiveMinimum": 0,
          "maximum": 10,
          "type": "number"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "cameraMedia",
        "backgroundMedia",
        "recordStartFrame",
        "durationFrames",
        "cameraTrackIndex",
        "backgroundTrackIndex"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.delete_through_edit",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "editFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "editFrameTolerance": {
          "maximum": 1000,
          "minimum": 0,
          "type": "integer"
        },
        "incoming": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "linkedAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 0,
          "type": "array"
        },
        "outgoing": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "outgoing",
        "incoming",
        "editFrame",
        "linkedAudioTargets"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.from_edl",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "expectedTimelineName": {
          "maxLength": 1024,
          "minLength": 1,
          "type": "string"
        },
        "inputArtifactId": {
          "maxLength": 160,
          "pattern": "^artifact_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "inputArtifactId",
        "expectedTimelineName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.remove",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "linkedAudio": {
          "const": "exclude"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "target": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "target",
        "recordFrame",
        "linkedAudio"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.remove_range",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "linkedAudio": {
          "const": "exclude"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "rangeEndFrameExclusive": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "type": "integer"
        },
        "rangeStartFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "targets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "video",
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "rangeStartFrame",
        "rangeEndFrameExclusive",
        "targets",
        "linkedAudio"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.ripple_delete",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "linkedAudio": {
          "const": "preserve"
        },
        "newTimelineName": {
          "maxLength": 1024,
          "minLength": 1,
          "pattern": "^(?=\\S(?:.*\\S)?$)[^\\\\/:\\n\\r\\t]+$",
          "type": "string"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "rangeEndFrameExclusive": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "type": "integer"
        },
        "rangeStartFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "targets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "video",
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "timelineFrameRate": {
          "exclusiveMinimum": 0,
          "maximum": 240,
          "type": "number"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "rangeStartFrame",
        "rangeEndFrameExclusive",
        "targets",
        "linkedAudio",
        "timelineFrameRate",
        "newTimelineName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.ripple_delete_selected",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "allOf": [
        {
          "else": {
            "properties": {
              "target": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "video"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              }
            }
          },
          "if": {
            "properties": {
              "scope": {
                "const": "audio"
              }
            }
          },
          "then": {
            "properties": {
              "target": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "audio"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              }
            }
          }
        }
      ],
      "properties": {
        "linkedAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 0,
          "type": "array"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "scope": {
          "enum": [
            "linked",
            "video",
            "audio"
          ]
        },
        "target": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "target",
        "recordFrame",
        "scope",
        "linkedAudioTargets"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.scene_detect",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "sourceTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "video"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "sourceTargets"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.slide_selected",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "direction": {
          "enum": [
            "left",
            "right"
          ]
        },
        "leftNeighbor": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "linkedAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 0,
          "type": "array"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "rightNeighbor": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "steps": {
          "maximum": 100,
          "minimum": 1,
          "type": "integer"
        },
        "target": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "target",
        "recordFrame",
        "direction",
        "steps",
        "linkedAudioTargets",
        "leftNeighbor",
        "rightNeighbor"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.slip_selected",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "direction": {
          "enum": [
            "left",
            "right"
          ]
        },
        "linkedAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 0,
          "type": "array"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "steps": {
          "maximum": 100,
          "minimum": 1,
          "type": "integer"
        },
        "target": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "target",
        "recordFrame",
        "direction",
        "steps",
        "linkedAudioTargets"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.social_crop",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "format": {
          "enum": [
            "9:16",
            "1:1",
            "4:5",
            "16:9"
          ]
        },
        "pan": {
          "maximum": 10,
          "minimum": -10,
          "type": "number"
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "setTimelineResolution": {
          "const": true
        },
        "sourceAspect": {
          "pattern": "^[1-9][0-9]{0,4}:[1-9][0-9]{0,4}$",
          "type": "string"
        },
        "targets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "video"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "tilt": {
          "maximum": 10,
          "minimum": -10,
          "type": "number"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "zoom": {
          "exclusiveMinimum": 0,
          "maximum": 10,
          "type": "number"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "targets",
        "format",
        "sourceAspect",
        "setTimelineResolution"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.split",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "linkedAudio": {
          "enum": [
            "preserve",
            "exclude"
          ]
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "recordFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "respectLocks": {
          "const": true
        },
        "targets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "video",
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 1,
          "type": "array"
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "recordFrame",
        "targets",
        "linkedAudio",
        "respectLocks"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.edit.transition.add",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "allOf": [
        {
          "else": {
            "properties": {
              "incoming": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "video"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              },
              "outgoing": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "video"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              }
            }
          },
          "if": {
            "properties": {
              "scope": {
                "const": "audio"
              }
            }
          },
          "then": {
            "properties": {
              "incoming": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "audio"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              },
              "outgoing": {
                "additionalProperties": false,
                "properties": {
                  "id": {
                    "maxLength": 160,
                    "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "linkedItemIds": {
                    "items": {
                      "maxLength": 160,
                      "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                      "type": "string"
                    },
                    "maxItems": 64,
                    "type": "array",
                    "uniqueItems": true
                  },
                  "mediaPoolItemId": {
                    "oneOf": [
                      {
                        "maxLength": 160,
                        "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                        "type": "string"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "name": {
                    "maxLength": 4096,
                    "minLength": 1,
                    "type": "string"
                  },
                  "recordEndFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "recordStartFrame": {
                    "maximum": 9007199254740991,
                    "minimum": 0,
                    "type": "integer"
                  },
                  "snapshotId": {
                    "maxLength": 160,
                    "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  "trackIndex": {
                    "maximum": 4096,
                    "minimum": 1,
                    "type": "integer"
                  },
                  "trackType": {
                    "enum": [
                      "audio"
                    ]
                  }
                },
                "required": [
                  "snapshotId",
                  "id",
                  "trackType",
                  "trackIndex",
                  "recordStartFrame",
                  "recordEndFrame",
                  "name",
                  "mediaPoolItemId",
                  "linkedItemIds"
                ],
                "type": "object"
              }
            }
          }
        }
      ],
      "properties": {
        "durationFrames": {
          "maximum": 9007199254740991,
          "minimum": 1,
          "type": "integer"
        },
        "editFrame": {
          "maximum": 9007199254740991,
          "minimum": 0,
          "type": "integer"
        },
        "incoming": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "linkedAudioTargets": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "id": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "linkedItemIds": {
                "items": {
                  "maxLength": 160,
                  "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                "maxItems": 64,
                "type": "array",
                "uniqueItems": true
              },
              "mediaPoolItemId": {
                "oneOf": [
                  {
                    "maxLength": 160,
                    "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                    "type": "string"
                  },
                  {
                    "type": "null"
                  }
                ]
              },
              "name": {
                "maxLength": 4096,
                "minLength": 1,
                "type": "string"
              },
              "recordEndFrame": {
                "maximum": 9007199254740991,
                "minimum": 1,
                "type": "integer"
              },
              "recordStartFrame": {
                "maximum": 9007199254740991,
                "minimum": 0,
                "type": "integer"
              },
              "snapshotId": {
                "maxLength": 160,
                "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "trackIndex": {
                "maximum": 4096,
                "minimum": 1,
                "type": "integer"
              },
              "trackType": {
                "enum": [
                  "audio"
                ]
              }
            },
            "required": [
              "snapshotId",
              "id",
              "trackType",
              "trackIndex",
              "recordStartFrame",
              "recordEndFrame",
              "name",
              "mediaPoolItemId",
              "linkedItemIds"
            ],
            "type": "object"
          },
          "maxItems": 4096,
          "minItems": 0,
          "type": "array"
        },
        "outgoing": {
          "additionalProperties": false,
          "properties": {
            "id": {
              "maxLength": 160,
              "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "linkedItemIds": {
              "items": {
                "maxLength": 160,
                "pattern": "^timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                "type": "string"
              },
              "maxItems": 64,
              "type": "array",
              "uniqueItems": true
            },
            "mediaPoolItemId": {
              "oneOf": [
                {
                  "maxLength": 160,
                  "pattern": "^media_pool_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
                  "type": "string"
                },
                {
                  "type": "null"
                }
              ]
            },
            "name": {
              "maxLength": 4096,
              "minLength": 1,
              "type": "string"
            },
            "recordEndFrame": {
              "maximum": 9007199254740991,
              "minimum": 1,
              "type": "integer"
            },
            "recordStartFrame": {
              "maximum": 9007199254740991,
              "minimum": 0,
              "type": "integer"
            },
            "snapshotId": {
              "maxLength": 160,
              "pattern": "^snapshot_timeline_item_[A-Za-z0-9][A-Za-z0-9._~-]*$",
              "type": "string"
            },
            "trackIndex": {
              "maximum": 4096,
              "minimum": 1,
              "type": "integer"
            },
            "trackType": {
              "enum": [
                "video",
                "audio"
              ]
            }
          },
          "required": [
            "snapshotId",
            "id",
            "trackType",
            "trackIndex",
            "recordStartFrame",
            "recordEndFrame",
            "name",
            "mediaPoolItemId",
            "linkedItemIds"
          ],
          "type": "object"
        },
        "placement": {
          "enum": [
            "start",
            "end",
            "both"
          ]
        },
        "projectId": {
          "maxLength": 160,
          "pattern": "^project_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "scope": {
          "enum": [
            "linked",
            "video",
            "audio"
          ]
        },
        "timelineId": {
          "maxLength": 160,
          "pattern": "^timeline_(?!item_)[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "timelineRevision": {
          "maxLength": 160,
          "pattern": "^revision_[A-Za-z0-9][A-Za-z0-9._~-]*$",
          "type": "string"
        },
        "transitionType": {
          "maxLength": 256,
          "minLength": 1,
          "type": "string"
        }
      },
      "required": [
        "projectId",
        "timelineId",
        "timelineRevision",
        "outgoing",
        "incoming",
        "linkedAudioTargets",
        "editFrame",
        "transitionType",
        "durationFrames",
        "placement",
        "scope"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.insert",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "boldStyle": {
          "minLength": 1,
          "type": "string"
        },
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "duration": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "duration"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "minimum": 0,
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "recordPosition": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "timeline_record"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "templatePath": {
          "minLength": 1,
          "type": "string"
        },
        "text": {
          "minLength": 1,
          "type": "string"
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "text"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.insert_preset",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "allowPartialFields": {
          "type": "boolean"
        },
        "boldStyle": {
          "minLength": 1,
          "type": "string"
        },
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "duration": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "duration"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "minimum": 0,
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "kind": {
          "enum": [
            "auto",
            "title",
            "fusion_title"
          ]
        },
        "presetName": {
          "minLength": 1,
          "type": "string"
        },
        "recordPosition": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "timeline_record"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "text": {
          "type": "string"
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "presetName"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.insert_template",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "boldStyle": {
          "minLength": 1,
          "type": "string"
        },
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "containerKind": {
          "enum": [
            "fusion",
            "textplus"
          ]
        },
        "containerPreset": {
          "minLength": 1,
          "type": "string"
        },
        "duration": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "duration"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "minimum": 0,
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "imagePath": {
          "minLength": 1,
          "type": "string"
        },
        "recordPosition": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "timeline_record"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "requireImage": {
          "type": "boolean"
        },
        "requireStyling": {
          "type": "boolean"
        },
        "requireText": {
          "type": "boolean"
        },
        "styleMarkdown": {
          "type": "boolean"
        },
        "templatePath": {
          "minLength": 1,
          "type": "string"
        },
        "text": {
          "type": "string"
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "templatePath"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.insert_template_batch",
    "operationClass": "mutation",
    "authority": "exact_project_timeline_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "allowCreateTrack": {
          "type": "boolean"
        },
        "allowNonEmptyTrack": {
          "type": "boolean"
        },
        "boldStyle": {
          "minLength": 1,
          "type": "string"
        },
        "cleanupOnFailure": {
          "type": "boolean"
        },
        "containerKind": {
          "enum": [
            "fusion",
            "textplus"
          ]
        },
        "containerPreset": {
          "minLength": 1,
          "type": "string"
        },
        "imagePath": {
          "minLength": 1,
          "type": "string"
        },
        "items": {
          "items": {
            "additionalProperties": false,
            "properties": {
              "clipName": {
                "minLength": 1,
                "type": "string"
              },
              "duration": {
                "additionalProperties": false,
                "properties": {
                  "domain": {
                    "const": "duration"
                  },
                  "value": {
                    "additionalProperties": false,
                    "properties": {
                      "kind": {
                        "const": "frames"
                      },
                      "value": {
                        "minimum": 0,
                        "type": "integer"
                      }
                    },
                    "required": [
                      "kind",
                      "value"
                    ],
                    "type": "object"
                  }
                },
                "required": [
                  "domain",
                  "value"
                ],
                "type": "object"
              },
              "imagePath": {
                "minLength": 1,
                "type": "string"
              },
              "recordPosition": {
                "additionalProperties": false,
                "properties": {
                  "domain": {
                    "const": "timeline_record"
                  },
                  "value": {
                    "additionalProperties": false,
                    "properties": {
                      "kind": {
                        "const": "frames"
                      },
                      "value": {
                        "type": "integer"
                      }
                    },
                    "required": [
                      "kind",
                      "value"
                    ],
                    "type": "object"
                  }
                },
                "required": [
                  "domain",
                  "value"
                ],
                "type": "object"
              },
              "replacements": {
                "items": {
                  "minLength": 1,
                  "type": "string"
                },
                "type": "array"
              },
              "text": {
                "minLength": 1,
                "type": "string"
              }
            },
            "required": [
              "text",
              "recordPosition",
              "duration"
            ],
            "type": "object"
          },
          "maxItems": 1000,
          "minItems": 1,
          "type": "array"
        },
        "replacements": {
          "items": {
            "minLength": 1,
            "type": "string"
          },
          "type": "array"
        },
        "requireAboveOccupied": {
          "type": "boolean"
        },
        "requireImage": {
          "type": "boolean"
        },
        "requireStyling": {
          "type": "boolean"
        },
        "requireText": {
          "type": "boolean"
        },
        "styleMarkdown": {
          "type": "boolean"
        },
        "templatePath": {
          "minLength": 1,
          "type": "string"
        },
        "trackPolicy": {
          "enum": [
            "empty-above-occupied",
            "requested"
          ]
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "templatePath",
        "items"
      ],
      "type": "object"
    }
  },
  {
    "actionId": "cutagent.action.text.update",
    "operationClass": "mutation",
    "authority": "exact_timeline_item_revision",
    "inputSchema": {
      "additionalProperties": false,
      "properties": {
        "allowPartialFields": {
          "type": "boolean"
        },
        "boldStyle": {
          "minLength": 1,
          "type": "string"
        },
        "clipName": {
          "minLength": 1,
          "type": "string"
        },
        "doubleSpaces": {
          "type": "boolean"
        },
        "recordPosition": {
          "additionalProperties": false,
          "properties": {
            "domain": {
              "const": "timeline_record"
            },
            "value": {
              "additionalProperties": false,
              "properties": {
                "kind": {
                  "const": "frames"
                },
                "value": {
                  "type": "integer"
                }
              },
              "required": [
                "kind",
                "value"
              ],
              "type": "object"
            }
          },
          "required": [
            "domain",
            "value"
          ],
          "type": "object"
        },
        "role": {
          "enum": [
            "body",
            "header"
          ]
        },
        "styled": {
          "type": "boolean"
        },
        "text": {
          "type": "string"
        },
        "toolName": {
          "minLength": 1,
          "type": "string"
        },
        "uppercase": {
          "type": "boolean"
        },
        "videoTrackIndex": {
          "minimum": 1,
          "type": "integer"
        }
      },
      "required": [
        "text"
      ],
      "type": "object"
    }
  }
];
