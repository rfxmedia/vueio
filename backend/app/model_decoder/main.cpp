// One purpose: turn an Ogawa polygon-mesh cache into bounded review frames.
#include <Alembic/AbcGeom/All.h>
#include <Alembic/AbcCoreOgawa/All.h>
#include <mapbox/earcut.hpp>
#include <zlib.h>
#include <sys/resource.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <vector>

namespace A = Alembic::Abc;
namespace G = Alembic::AbcGeom;
namespace fs = std::filesystem;
using Imath::M44d;
using Imath::V3f;
constexpr size_t maxVertices = 750000;

static void require(bool ok) { if (!ok) throw std::runtime_error("Invalid or oversized mesh cache"); }
static void limit(int kind, rlim_t value) {
    rlimit budget{value, value};
    require(setrlimit(kind, &budget) == 0);
}

struct Timing {
    double first = std::numeric_limits<double>::max(), last = -std::numeric_limits<double>::max();
    double step = 0;
    void add(Alembic::AbcCoreAbstract::TimeSamplingPtr sampling, size_t count) {
        if (count <= 1) return;
        require(count <= 1000000);
        double start = sampling->getSampleTime(0), end = sampling->getSampleTime(count - 1);
        require(std::isfinite(start) && std::isfinite(end) && end >= start);
        first = std::min(first, start); last = std::max(last, end);
        if (sampling->getTimeSamplingType().isUniform()) {
            const double interval = sampling->getSampleTime(1) - start;
            if (interval > 0) step = step ? std::min(step, interval) : interval;
        }
    }
};

static void inspect(A::IObject object, Timing& timing, size_t& count, unsigned depth = 0) {
    require(depth < 64 && ++count <= 10000);
    auto header = object.getHeader();
    if (G::IPolyMesh::matches(header)) {
        auto schema = G::IPolyMesh(object, A::kWrapExisting).getSchema();
        timing.add(schema.getTimeSampling(), schema.getNumSamples());
    } else if (G::IXform::matches(header)) {
        auto schema = G::IXform(object, A::kWrapExisting).getSchema();
        timing.add(schema.getTimeSampling(), schema.getNumSamples());
    } else {
        // Do not quietly omit points, curves, subdivision surfaces, or volumes.
        require(object.getParent().valid() == false || G::ICamera::matches(header) || G::IFaceSet::matches(header));
    }
    auto visibility = G::GetVisibilityProperty(object);
    if (visibility.valid()) timing.add(visibility.getTimeSampling(), visibility.getNumSamples());
    for (size_t i = 0; i < object.getNumChildren(); ++i) inspect(object.getChild(i), timing, count, depth + 1);
}

struct Frame {
    std::vector<V3f> positions, normals;
    void mesh(A::IObject object, const M44d& transform, const A::ISampleSelector& at) {
        auto schema = G::IPolyMesh(object, A::kWrapExisting).getSchema();
        G::IPolyMeshSchema::Sample sample;
        schema.get(sample, at);
        require(sample.valid());
        auto points = sample.getPositions();
        auto indices = sample.getFaceIndices();
        auto counts = sample.getFaceCounts();
        require(points->size() <= 1000000 && indices->size() <= 1500000 && counts->size() <= 250000);
        G::IN3fGeomParam::Sample normalSample;
        auto normalParam = schema.getNormalsParam();
        if (normalParam.valid()) normalParam.getExpanded(normalSample, at);
        auto normalValues = normalSample.getVals();
        const auto normalTransform = transform.inverse().transposed();
        size_t offset = 0;
        for (size_t face = 0; face < counts->size(); ++face) {
            const auto count = (*counts)[face];
            require(count >= 3 && count <= 10000 && offset + count <= indices->size());
            std::vector<V3f> polygon;
            for (int corner = 0; corner < count; ++corner) {
                auto index = (*indices)[offset + corner];
                require(index >= 0 && size_t(index) < points->size());
                V3f p;
                transform.multVecMatrix((*points)[index], p);
                require(std::isfinite(p.x) && std::isfinite(p.y) && std::isfinite(p.z)
                        && std::abs(p.x) < 1e9 && std::abs(p.y) < 1e9 && std::abs(p.z) < 1e9);
                polygon.push_back(p);
            }
            // Newell's normal gives a stable plane for concave n-gons.
            V3f normal(0);
            for (int i = 0; i < count; ++i) {
                const auto& p = polygon[i]; const auto& q = polygon[(i + 1) % count];
                normal.x += (p.y - q.y) * (p.z + q.z);
                normal.y += (p.z - q.z) * (p.x + q.x);
                normal.z += (p.x - q.x) * (p.y + q.y);
            }
            const int axis = std::abs(normal.x) > std::abs(normal.y)
                ? (std::abs(normal.x) > std::abs(normal.z) ? 0 : 2)
                : (std::abs(normal.y) > std::abs(normal.z) ? 1 : 2);
            std::vector<std::vector<std::array<double, 2>>> rings(1);
            for (const auto& p : polygon) rings[0].push_back({p[(axis + 1) % 3], p[(axis + 2) % 3]});
            auto triangles = mapbox::earcut<uint32_t>(rings);
            require(positions.size() + triangles.size() <= maxVertices);
            for (size_t tri = 0; tri + 2 < triangles.size(); tri += 3) {
                if ((polygon[triangles[tri + 1]] - polygon[triangles[tri]]).cross(polygon[triangles[tri + 2]] - polygon[triangles[tri]]).dot(normal) < 0)
                    std::swap(triangles[tri + 1], triangles[tri + 2]);
                // A mirrored transform changes winding, but not the outside.
                if (transform.determinant() < 0) std::swap(triangles[tri + 1], triangles[tri + 2]);
                V3f fallback = (polygon[triangles[tri + 1]] - polygon[triangles[tri]]).cross(polygon[triangles[tri + 2]] - polygon[triangles[tri]]);
                fallback.normalize();
                for (int c = 0; c < 3; ++c) {
                    auto corner = triangles[tri + c];
                    V3f n = fallback;
                    if (normalValues && normalValues->size()) {
                        size_t index = 0;
                        switch (normalParam.getScope()) {
                            case G::kFacevaryingScope: index = offset + corner; break;
                            case G::kVaryingScope: case G::kVertexScope: index = (*indices)[offset + corner]; break;
                            case G::kUniformScope: index = face; break;
                            case G::kConstantScope: break;
                            default: throw std::runtime_error("Invalid normal scope");
                        }
                        require(index < normalValues->size());
                        normalTransform.multDirMatrix((*normalValues)[index], n);
                        n.normalize();
                    }
                    require(std::isfinite(n.x) && std::isfinite(n.y) && std::isfinite(n.z));
                    positions.push_back(polygon[corner]); normals.push_back(n);
                }
            }
            offset += count;
        }
        require(offset == indices->size());
    }
    void visit(A::IObject object, M44d transform, const A::ISampleSelector& at, bool visible = true) {
        const auto visibility = G::GetVisibility(object, at);
        if (visibility == G::kVisibilityHidden) visible = false;
        if (G::IXform::matches(object.getHeader())) {
            auto schema = G::IXform(object, A::kWrapExisting).getSchema();
            auto sample = schema.getValue(at);
            transform = sample.getInheritsXforms() ? sample.getMatrix() * transform : sample.getMatrix();
        } else if (visible && G::IPolyMesh::matches(object.getHeader())) mesh(object, transform, at);
        for (size_t i = 0; i < object.getNumChildren(); ++i) visit(object.getChild(i), transform, at, visible);
    }
    uintmax_t write(const fs::path& directory, size_t index) {
        static_assert(sizeof(V3f) == 12, "Packed float3 required");
        char name[24]; snprintf(name, sizeof(name), "%05zu.bin.gz", index);
        auto temporary = directory / "frame.tmp";
        gzFile file = gzopen(temporary.c_str(), "wb1");
        require(file != nullptr);
        uint32_t header[] = {0x314d5556, uint32_t(positions.size())};
        const auto bytes = positions.size() * sizeof(V3f);
        bool ok = gzwrite(file, header, sizeof(header)) == sizeof(header);
        if (bytes) {
            ok = gzwrite(file, positions.data(), bytes) == int(bytes) && ok;
            ok = gzwrite(file, normals.data(), bytes) == int(bytes) && ok;
        }
        ok = gzclose(file) == Z_OK && ok;
        require(ok);
        auto size = fs::file_size(temporary);
        fs::rename(temporary, directory / name);
        return size;
    }
};

int main(int argc, char** argv) {
    try {
        require(argc == 3);
        limit(RLIMIT_CPU, 240); limit(RLIMIT_FSIZE, 64 * 1024 * 1024);
#ifdef __linux__
        limit(RLIMIT_AS, 1ULL * 1024 * 1024 * 1024);
#endif
        A::IArchive archive(Alembic::AbcCoreOgawa::ReadArchive(1, false), argv[1], A::ErrorHandler::kThrowPolicy);
        Timing timing; size_t objects = 0;
        inspect(archive.getTop(), timing, objects);
        if (timing.last < timing.first) timing.first = timing.last = 0;
        std::string writer, version, date, description; uint32_t apiVersion; double fps = 0;
        A::GetArchiveInfo(archive, writer, version, apiVersion, date, description, fps);
        if (!std::isfinite(fps) || fps < 1 || fps > 120) fps = timing.step > 0 ? 1 / timing.step : 30;
        fps = std::clamp(fps, 1., 120.);
        const double duration = timing.last - timing.first;
        require(std::isfinite(duration) && duration >= 0 && duration <= 2400 / fps);
        const size_t frames = size_t(std::ceil(duration * fps - 1e-6)) + 1;
        require(frames <= 2400);
        fs::path directory(argv[2]); uintmax_t bytes = 0;
        for (size_t index = 0; index < frames; ++index) {
            Frame frame;
            frame.visit(archive.getTop(), M44d(), A::ISampleSelector(timing.first + index / fps, A::ISampleSelector::kNearIndex));
            bytes += frame.write(directory, index);
            require(bytes <= 512ULL * 1024 * 1024);
            auto temporary = directory / "manifest.tmp";
            std::ofstream metadata(temporary);
            metadata << std::setprecision(12) << "{\"status\":\"" << (index + 1 == frames ? "complete" : "processing")
                << "\",\"frame_count\":" << frames << ",\"ready_frames\":" << index + 1
                << ",\"fps\":" << fps << ",\"duration\":" << duration << ",\"source_start\":" << timing.first
                << ",\"progress\":" << (index + 1) * 100 / frames << "}";
            metadata.close(); require(bool(metadata));
            fs::rename(temporary, directory / "manifest.json");
        }
        return 0;
    } catch (...) { return 1; }
}
