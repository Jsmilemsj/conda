# -*- coding: utf-8 -*-
"""
                         +----------------+
                         | BasePackageRef |
                         +-------+--------+
                                 |
              +------------+     |     +-----------------+
              | PackageRef <-----+-----> IndexJsonRecord |
              +------+-----+           +-------+---------+
                     |                         |
                     +-----------+-------------+
                                 |
                         +-------v-------+
                         | PackageRecord |
                         +--+---------+--+
+--------------------+      |         |      +--------------+
| PackageCacheRecord <------+         +------> PrefixRecord |
+--------------------+                       +--------------+


"""
from __future__ import absolute_import, division, print_function, unicode_literals

from functools import total_ordering

from .channel import Channel
from .enums import FileMode, LinkType, NoarchType, PackageType, PathType, Platform
from .._vendor.auxlib.entity import (BooleanField, ComposableField, DictSafeMixin, Entity,
                                     EnumField, Field, IntegerField, ListField, StringField)
from ..base.context import context
from ..common.compat import isiterable, itervalues, string_types, text_type


@total_ordering
class Priority(object):

    def __init__(self, priority):
        self._priority = priority

    def __int__(self):
        return self._priority

    def __lt__(self, other):
        return self._priority < int(other)

    def __eq__(self, other):
        return self._priority == int(other)

    def __repr__(self):
        return "Priority(%d)" % self._priority


class PriorityField(Field):
    _type = (int, Priority)

    def unbox(self, instance, instance_type, val):
        return int(val)


class LinkTypeField(EnumField):
    def box(self, instance, val):
        if isinstance(val, string_types):
            val = val.replace('-', '').replace('_', '').lower()
            if val == 'hard':
                val = LinkType.hardlink
            elif val == 'soft':
                val = LinkType.softlink
        return super(LinkTypeField, self).box(instance, val)


class NoarchField(EnumField):
    def box(self, instance, val):
        return super(NoarchField, self).box(instance, NoarchType.coerce(val))


class Link(DictSafeMixin, Entity):
    source = StringField()
    type = LinkTypeField(LinkType, required=False)


EMPTY_LINK = Link(source='')


class FeaturesField(ListField):

    def __init__(self, **kwargs):
        super(FeaturesField, self).__init__(string_types, **kwargs)

    def box(self, instance, val):
        if isinstance(val, string_types):
            val = val.replace(' ', ',').split(',')
        return super(FeaturesField, self).box(instance, val)

    def dump(self, val):
        if isiterable(val):
            return ' '.join(val)
        else:
            return val or ''


class ChannelField(ComposableField):

    def __init__(self, aliases=()):
        self._type = Channel
        super(ComposableField, self).__init__(required=False, aliases=aliases)

    def dump(self, val):
        return val and text_type(val)

    def __get__(self, instance, instance_type):
        try:
            return super(ChannelField, self).__get__(instance, instance_type)
        except AttributeError:
            try:
                url = instance.url
                return self.unbox(instance, instance_type, Channel(url))
            except AttributeError:
                return Channel(None)


class SubdirField(StringField):

    def __init__(self):
        super(SubdirField, self).__init__(required=False)

    def __get__(self, instance, instance_type):
        try:
            return super(SubdirField, self).__get__(instance, instance_type)
        except AttributeError:
            try:
                url = instance.url
            except AttributeError:
                url = None
            if url:
                return self.unbox(instance, instance_type, Channel(url).subdir)

            try:
                platform, arch = instance.platform.name, instance.arch
            except AttributeError:
                platform, arch = None, None
            if platform and not arch:
                return self.unbox(instance, instance_type, 'noarch')
            elif platform:
                if 'x86' in arch:
                    arch = '64' if '64' in arch else '32'
                return self.unbox(instance, instance_type, '%s-%s' % (platform, arch))
            else:
                return self.unbox(instance, instance_type, context.subdir)


class FilenameField(StringField):

    def __init__(self, aliases=()):
        super(FilenameField, self).__init__(required=False, aliases=aliases)

    def __get__(self, instance, instance_type):
        try:
            return super(FilenameField, self).__get__(instance, instance_type)
        except AttributeError:
            try:
                url = instance.url
                fn = Channel(url).package_filename
                if not fn:
                    raise AttributeError()
            except AttributeError:
                fn = '%s-%s-%s' % (instance.name, instance.version, instance.build)
            assert fn
            return self.unbox(instance, instance_type, fn)


class PathData(Entity):
    _path = StringField()
    prefix_placeholder = StringField(required=False, nullable=True, default=None,
                                     default_in_dump=False)
    file_mode = EnumField(FileMode, required=False, nullable=True)
    no_link = BooleanField(required=False, nullable=True, default=None, default_in_dump=False)
    path_type = EnumField(PathType)

    @property
    def path(self):
        # because I don't have aliases as an option for entity fields yet
        return self._path


class PathDataV1(PathData):
    # TODO: sha256 and size_in_bytes should be required for all PathType.hardlink, but not for softlink and directory  # NOQA
    sha256 = StringField(required=False, nullable=True)
    size_in_bytes = IntegerField(required=False, nullable=True)
    inode_paths = ListField(string_types, required=False, nullable=True)

    sha256_in_prefix = StringField(required=False, nullable=True)


class PathsData(Entity):
    # from info/paths.json
    paths_version = IntegerField()
    paths = ListField(PathData)


class BasePackageRef(DictSafeMixin, Entity):
    name = StringField()
    version = StringField()
    build = StringField(aliases=('build_string',))
    build_number = IntegerField()


class PackageRef(BasePackageRef):
    # the canonical code abbreviation for PackageRef is `pref`
    # fields required to uniquely identifying a package

    channel = ChannelField(aliases=('schannel',))
    subdir = SubdirField()
    fn = FilenameField(aliases=('filename',))

    md5 = StringField(default=None, required=False, nullable=True, default_in_dump=False)
    url = StringField(required=False, nullable=True)

    @property
    def schannel(self):
        return self.channel.canonical_name

    @property
    def _pkey(self):
        return self.channel.canonical_name, self.subdir, self.name, self.version, self.build

    def __hash__(self):
        return hash(self._pkey)

    def __eq__(self, other):
        return self._pkey == other._pkey

    def dist_str(self):
        return "%s::%s-%s-%s" % (self.channel.canonical_name, self.name, self.version, self.build)


class IndexJsonRecord(BasePackageRef):

    arch = StringField(required=False, nullable=True)  # so legacy
    platform = EnumField(Platform, required=False, nullable=True)  # so legacy

    depends = ListField(string_types, default=())
    constrains = ListField(string_types, default=())

    features = FeaturesField(required=False, default=(), default_in_dump=False)
    track_features = FeaturesField(required=False, default=(), default_in_dump=False)

    subdir = SubdirField()
    # package_type = EnumField(NoarchType, required=False)  # previously noarch
    noarch = NoarchField(NoarchType, required=False, nullable=True, default=None,
                         default_in_dump=False)  # TODO: rename to package_type
    preferred_env = StringField(required=False, nullable=True, default=None, default_in_dump=False)

    license = StringField(required=False)
    license_family = StringField(required=False)

    @property
    def combined_depends(self):
        from .match_spec import MatchSpec
        result = {ms.name: ms for ms in (MatchSpec(spec) for spec in self.depends or ())}
        result.update({ms.name: ms for ms in (MatchSpec(spec, optional=True)
                                              for spec in self.constrains or ())})
        return tuple(itervalues(result))


class PackageRecord(IndexJsonRecord, PackageRef):
    # the canonical code abbreviation for PackageRecord is `prec`, not to be confused with
    # PackageCacheRecord (`pcrec`) or PrefixRecord (`prefix_rec`)
    #
    # important for "choosing" a package (i.e. the solver), listing packages
    # (like search), and for verifying downloads
    #
    # this is the highest level of the record inheritance model that MatchSpec is designed to
    # work with

    date = StringField(required=False)
    priority = PriorityField(required=False)
    size = IntegerField(required=False)

    package_type = EnumField(PackageType, required=False, nullable=True)


IndexRecord = PackageRecord

# class IndexRecord(DictSafeMixin, Entity):
#     _lazy_validate = True
#
#     arch = StringField(required=False, nullable=True)
#     build = StringField()
#     build_number = IntegerField()
#     constrains = ListField(string_types, required=False, nullable=True)
#     date = StringField(required=False)
#     depends = ListField(string_types, required=False, nullable=True)
#     features = StringField(required=False)
#     has_prefix = BooleanField(required=False)
#     license = StringField(required=False)
#     license_family = StringField(required=False)
#     md5 = StringField(required=False, nullable=True)
#     name = StringField()
#     noarch = NoarchField(NoarchType, required=False, nullable=True)
#     platform = EnumField(Platform, required=False, nullable=True)
#     requires = ListField(string_types, required=False)
#     size = IntegerField(required=False)
#     subdir = StringField(required=False)
#     timestamp = IntegerField(required=False)
#     track_features = StringField(default='', required=False)
#     version = StringField()
#
#     fn = StringField(required=False, nullable=True)
#     schannel = StringField(required=False, nullable=True)
#     channel = StringField(required=False, nullable=True)
#     priority = PriorityField(required=False)
#     url = StringField(required=False, nullable=True)
#     auth = StringField(required=False, nullable=True)
#
#     files = ListField(string_types, default=(), required=False)
#     link = ComposableField(Link, required=False)
#
#     preferred_env = StringField(default=None, required=False, nullable=True)
#
#     # this is only for LinkedPackageRecord
#     leased_paths = ListField(LeasedPathEntry, required=False)
#
#     @property
#     def combined_depends(self):
#         from .match_spec import MatchSpec
#         result = {ms.name: ms for ms in (MatchSpec(spec) for spec in self.depends or ())}
#         result.update({ms.name: ms for ms in (MatchSpec(spec, optional=True)
#                                               for spec in self.constrains or ())})
#         return tuple(itervalues(result))
